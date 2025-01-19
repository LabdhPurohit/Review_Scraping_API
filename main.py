from flask import Flask, request, jsonify
from typing import List, Optional
from pydantic import BaseModel
import asyncio
from playwright.async_api import async_playwright
from transformers import pipeline

app = Flask(__name__)

generator = pipeline('text-generation', model='gpt2')

class Review(BaseModel):
    title: Optional[str]
    body: Optional[str]
    rating: Optional[float]
    reviewer: Optional[str]

class ReviewsResponse(BaseModel):
    reviews_count: int
    reviews: List[Review]

async def extract_reviews_with_playwright(url: str) -> List[Review]:
    reviews = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url)
        html_content = await page.content()

        css_selectors = identify_css_selectors(html_content)

        while True:
            review_elements = await page.query_selector_all(css_selectors['review_container'])

            for review_element in review_elements:
                title = await review_element.query_selector(css_selectors['title'])
                body = await review_element.query_selector(css_selectors['body'])
                rating = await review_element.query_selector(css_selectors['rating'])
                reviewer = await review_element.query_selector(css_selectors['reviewer'])

                rating_text = await rating.inner_text() if rating else ''
                rating_value = float(rating_text) if rating_text and rating_text.strip() else None

                reviews.append(Review(
                    title=await title.inner_text() if title else None,
                    body=await body.inner_text() if body else None,
                    rating=rating_value,
                    reviewer=await reviewer.inner_text() if reviewer else None,
                ))

            next_button = await page.query_selector(css_selectors.get('pagination_next'))
            if next_button and await next_button.is_enabled():
                await next_button.click()
                await page.wait_for_timeout(2000)
            else:
                break

        await browser.close()

    return reviews

def identify_css_selectors(html_content: str) -> dict:
    prompt = (
        f"Identify CSS selectors for review sections in this HTML snippet: {html_content[:1500]} "
        f"and structure them as a JSON dictionary with keys like review_container, title, body, rating, reviewer, and pagination_next."
    )
    generated_text = generator(prompt, max_length=300)[0]['generated_text']

    try:
        css_selectors = eval(generated_text.split('```')[1])
    except Exception:
        css_selectors = {
            "review_container": "div.review",
            "title": "h3.title",
            "body": "p.body",
            "rating": "span.rating",
            "reviewer": "span.reviewer",
            "pagination_next": "a.next"
        }

    return css_selectors

@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    page_url = request.args.get('page')
    if not page_url:
        return jsonify({"error": "Page URL is required"}), 400

    try:
        reviews = asyncio.run(extract_reviews_with_playwright(page_url))
        response = ReviewsResponse(reviews_count=len(reviews), reviews=reviews)
        return jsonify(response.dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
