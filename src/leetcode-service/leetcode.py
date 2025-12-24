import random

import httpx
from loguru import logger

LEETCODE_URL = "https://leetcode.com/graphql"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://leetcode.com",
    "Referer": "https://leetcode.com/problemset/all/",
    "Content-Type": "application/json",
}


async def get_random_question(difficulty: str = "EASY"):
    difficulty = difficulty.upper()

    max_skip = 400 if difficulty == "EASY" else 800
    skip = random.randint(0, max_skip)

    list_query = """
    query problemsetQuestionListV2($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionFilterInput) {
        problemsetQuestionListV2(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
            filters: $filters
        ) {
            questions {
                titleSlug
                title
                paidOnly
                difficulty
            }
        }
    }
    """

    list_variables = {
        "categorySlug": "all-code-essentials",
        "skip": skip,
        "limit": 50,
        "filters": {
            "filterCombineType": "ALL",
            "difficultyFilter": {"difficulties": [difficulty], "operator": "IS"},
            "statusFilter": {"questionStatuses": [], "operator": "IS"},
        },
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            logger.info(f"Fetching list: difficulty={difficulty}, skip={skip}")

            resp_list = await client.post(
                LEETCODE_URL,
                json={"query": list_query, "variables": list_variables},
                headers=HEADERS,
            )

            if resp_list.status_code != 200:
                logger.error(
                    f"List API Error {resp_list.status_code}: {resp_list.text}"
                )
                resp_list.raise_for_status()

            data_list = resp_list.json()

            if "errors" in data_list:
                logger.error(f"GraphQL Errors: {data_list['errors']}")
                raise Exception(
                    f"LeetCode API Error: {data_list['errors'][0]['message']}"
                )

            if (
                "data" not in data_list
                or not data_list["data"]["problemsetQuestionListV2"]
            ):
                logger.error(f"Empty Data: {data_list}")
                raise Exception("LeetCode returned empty list")

            questions = data_list["data"]["problemsetQuestionListV2"]["questions"]

            free_questions = [q for q in questions if not q.get("paidOnly")]

            if not free_questions:
                logger.warning("No free questions in batch, retrying...")
                raise Exception("No free questions found in this batch, try again")

            chosen_q = random.choice(free_questions)
            title_slug = chosen_q["titleSlug"]
            title = chosen_q["title"]

            logger.info(f"🎲 Selected: {title} ({title_slug})")

            content_query = """
            query questionContent($titleSlug: String!) {
                question(titleSlug: $titleSlug) {
                    content
                    codeSnippets {
                        lang
                        langSlug
                        code
                    }
                }
            }
            """

            resp_content = await client.post(
                LEETCODE_URL,
                json={
                    "query": content_query,
                    "variables": {"titleSlug": title_slug},
                },
                headers=HEADERS,
            )
            resp_content.raise_for_status()
            data_content = resp_content.json()

            q_data = data_content["data"]["question"]

            py_snippet = ""
            for s in q_data.get("codeSnippets", []) or []:
                if s["langSlug"] == "python3":
                    py_snippet = s["code"]
                    break

            if not py_snippet:
                for s in q_data.get("codeSnippets", []) or []:
                    if s["langSlug"] == "python":
                        py_snippet = s["code"]
                        break

            return {
                "title": title,
                "slug": title_slug,
                "content_html": q_data["content"],
                "initial_code": py_snippet,
                "link": f"https://leetcode.com/problems/{title_slug}/",
            }

        except Exception as e:
            logger.exception("Error in get_random_question")
            raise e


async def search_problems(keyword: str, limit: int = 5):
    """Поиск задач по ключевому слову"""
    query = """
    query problemsetQuestionListV2($categorySlug: String, $limit: Int, $filters: QuestionFilterInput, $searchKeyword: String) {
        problemsetQuestionListV2(
            categorySlug: $categorySlug
            limit: $limit
            filters: $filters
            searchKeyword: $searchKeyword
        ) {
            questions {
                titleSlug
                title
                difficulty
                paidOnly
            }
        }
    }
    """

    variables = {
        "categorySlug": "all-code-essentials",
        "limit": limit,
        "searchKeyword": keyword,
        "filters": {
            "filterCombineType": "ALL",
            "statusFilter": {"questionStatuses": [], "operator": "IS"},
        },
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                LEETCODE_URL,
                json={"query": query, "variables": variables},
                headers=HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()

            if "data" not in data or not data["data"]["problemsetQuestionListV2"]:
                return []

            questions = data["data"]["problemsetQuestionListV2"]["questions"]
            # Возвращаем только бесплатные
            return [q for q in questions if not q.get("paidOnly")]

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []


async def get_problem_by_slug(title_slug: str):
    async with httpx.AsyncClient(timeout=15.0) as client:
        content_query = """
        query questionContent($titleSlug: String!) {
            question(titleSlug: $titleSlug) {
                questionId
                title
                content
                codeSnippets {
                    lang
                    langSlug
                    code
                }
            }
        }
        """
        resp = await client.post(
            LEETCODE_URL,
            json={"query": content_query, "variables": {"titleSlug": title_slug}},
            headers=HEADERS,
        )
        data = resp.json()
        q_data = data["data"]["question"]

        py_snippet = ""
        for s in q_data.get("codeSnippets", []) or []:
            if s["langSlug"] == "python3":
                py_snippet = s["code"]
                break

        if not py_snippet:
            for s in q_data.get("codeSnippets", []) or []:
                if s["langSlug"] == "python":
                    py_snippet = s["code"]
                    break

        return {
            "title": q_data["title"],
            "slug": title_slug,
            "content_html": q_data["content"],
            "initial_code": py_snippet,
            "link": f"https://leetcode.com/problems/{title_slug}/",
        }
