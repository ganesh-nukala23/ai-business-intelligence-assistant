# AI Development Report

## 1. AI Tools Used

- **Claude (Anthropic), in a Claude Code session** – Used to generate the project structure, implementation, tests, and documentation based on the assessment instructions and sales dataset.
- **ChatGPT (OpenAI)** – Used for guidance on understanding the assessment requirements, reviewing the implementation, troubleshooting the local setup, and planning the final submission.
- **Runtime AI in the application** – Anthropic Messages API integration is implemented as an optional feature using `ANTHROPIC_API_KEY`. The application can also use rule-based interpretation when the API key is unavailable.

## 2. How AI Was Used

- The AI assistant analysed the assessment requirements and sales dataset, which contained 51 records and three edge cases:
  - TXN0033 – Returned transaction.
  - TXN0034 – Zero quantity.
  - TXN0051 – Missing unit price.
- It helped design the application using SQLite, a `valid_sales` database view, predefined SQL queries, and AI-assisted question interpretation.
- AI tools were used to generate the application code, automated tests, and documentation.
- The application separates question interpretation from numerical calculations: the AI identifies the requested operation, while SQL performs the actual calculations.
- **My contribution:** I reviewed the generated project and ran the setup and commands on my Windows laptop using Python 3.13.13. I executed the data loader, checked the loading results, ran the automated test suite, started the FastAPI server, and tested all five required business questions through the web interface. I also checked the error handling and confirmed that the rule-based fallback works without an API key.

## 3. Problems Encountered and How They Were Debugged

1. **Incorrect monthly trend results:** During development, a test identified seven months instead of six, including April with zero transactions. The issue was traced to ambiguous use of the `month` name in the SQL `GROUP BY` clause. The grouping expression was corrected, and the tests passed.

2. **Build environment issue:** The initial build environment had restrictions accessing PyPI, so a package was obtained from its GitHub source for testing in that environment. On my Windows laptop, I installed the dependencies using `requirements.txt` successfully.

3. **LLM API verification:** I did not have an Anthropic API key available during local testing. Therefore, I verified the rule-based fallback, but I could not verify a real Anthropic API request.

4. **Windows setup and testing:** I created the virtual environment, installed the dependencies, loaded the dataset into SQLite, and started the application locally. The application ran successfully, and I verified the five required questions through the browser.

5. **Dataset validation:** The data loader reported 51 records received, 51 loaded, and zero rejected. It excluded three records from revenue calculations because they were returned, had zero quantity, or had a missing unit price.

## 4. What Works and What Does Not

### Working and Verified

- CSV dataset loading into SQLite.
- Handling of the three identified edge cases.
- All five required business intelligence questions.
- Revenue calculations using SQL.
- Structured API responses and error handling.
- Rule-based question interpretation when the LLM API is unavailable.
- Web interface and local FastAPI server.
- Automated test suite: **79 tests passed** on my Windows laptop.

### Not Verified or Not Implemented

- A real Anthropic API request was not verified because an API key was unavailable.
- Product, region, and channel filters are not implemented.
- Follow-up questions and multi-turn conversations are not implemented.
- Authentication is not implemented.
- Analysis across additional years is not implemented.

## 5. Possible Improvements With Another Day of Work

- Test the LLM integration using a valid Anthropic API key.
- Improve fallback interpretation for differently phrased questions.
- Add structured LLM output validation.
- Add parameterised SQL templates for product, region, and channel filters.
- Add charts for monthly revenue trends.
- Support follow-up questions and conversation context.
- Add GitHub Actions for automated testing and Docker support.