# -*- coding: utf-8 -*-
# app/api/v1/ai_analyst.py

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.services.security import get_current_user_optional

router = APIRouter(tags=["AI Analyst"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/ai-analyst")
async def ai_analyst_page(request: Request, current_user = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "modules/ai_analyst.html",
        {"request": request, "current_user": current_user}
    )
