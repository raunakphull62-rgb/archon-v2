import logging
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agents import analyzer_agent, planner_agent, code_generator_agent
from builder import project_builder
from github import github_push

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Code Generation API",
    version="1.0.0",
    description="Transforms a prompt into a GitHub repository via agent pipeline.",
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User input prompt")


class GenerateResponse(BaseModel):
    repo_url: str = Field(..., description="URL of the generated GitHub repository")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Run agent pipeline and push generated project to GitHub",
)
async def generate(request: GenerateRequest) -> GenerateResponse:
    prompt = request.prompt
    logger.info("Received /generate request | prompt_length=%d", len(prompt))

    try:
        logger.info("Step 1/5 — Running analyzer_agent")
        analysis = await analyzer_agent(prompt)

        logger.info("Step 2/5 — Running planner_agent")
        plan = await planner_agent(analysis)

        logger.info("Step 3/5 — Running code_generator_agent")
        generated_code = await code_generator_agent(plan)

        logger.info("Step 4/5 — Running project_builder")
        project = await project_builder(generated_code)

        logger.info("Step 5/5 — Running github_push")
        repo_url = await github_push(project)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {exc}",
        ) from exc

    logger.info("Pipeline completed | repo_url=%s", repo_url)
    return GenerateResponse(repo_url=repo_url)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", status_code=status.HTTP_200_OK, include_in_schema=False)
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
