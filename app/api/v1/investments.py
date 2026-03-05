# -*- coding: utf-8 -*-
# app/api/v1/investments.py

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.services.security import get_current_user_optional

router = APIRouter(tags=["Investments"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/investments")
async def investments_page(request: Request, current_user = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "modules/investments.html",
        {"request": request, "current_user": current_user}
    )
