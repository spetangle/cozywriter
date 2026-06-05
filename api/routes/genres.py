"""小说题材 API - 系统内置 + 用户自定义"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from storage.database import get_db
from storage.models import CustomGenre


router = APIRouter(prefix="/api/genres", tags=["题材"])


# 系统预设题材（与历史数据兼容）
SYSTEM_GENRES = [
    "玄幻", "都市", "科幻", "武侠", "仙侠", "历史",
    "悬疑", "现实主义", "奇幻", "其他",
]


# ─── Schemas ───

class GenreCreate(BaseModel):
    name: str


class GenreResponse(BaseModel):
    id: int
    name: str
    is_system: bool
    created_at: object

    class Config:
        from_attributes = True


# ─── Routes ───

@router.get("", response_model=list[GenreResponse])
async def list_genres(db: Session = Depends(get_db)):
    """列出所有题材（系统 + 用户）"""
    system_rows = [GenreResponse(
        id=-(i+1),  # 负 id 表示系统预设（避免与 DB id 冲突）
        name=name,
        is_system=True,
        created_at=None,
    ) for i, name in enumerate(SYSTEM_GENRES)]
    user_rows = db.query(CustomGenre).order_by(CustomGenre.created_at.asc()).all()
    return system_rows + [GenreResponse.model_validate(r) for r in user_rows]


@router.post("", response_model=GenreResponse)
async def create_genre(data: GenreCreate, db: Session = Depends(get_db)):
    """用户自添加题材（去重）"""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="题材名不能为空")
    if name in SYSTEM_GENRES:
        raise HTTPException(status_code=400, detail=f"'{name}' 是系统预设题材，无需添加")
    if len(name) > 50:
        raise HTTPException(status_code=400, detail="题材名过长（>50 字符）")

    # 查重
    existing = db.query(CustomGenre).filter(CustomGenre.name == name).first()
    if existing:
        return GenreResponse.model_validate(existing)

    genre = CustomGenre(name=name, is_system=0)
    db.add(genre)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(CustomGenre).filter(CustomGenre.name == name).first()
        return GenreResponse.model_validate(existing)
    db.refresh(genre)
    return GenreResponse.model_validate(genre)


@router.delete("/{genre_id}")
async def delete_genre(genre_id: int, db: Session = Depends(get_db)):
    """删除用户自添加的题材（系统预设不可删）"""
    if genre_id < 0:
        raise HTTPException(status_code=400, detail="系统预设题材不可删除")
    genre = db.query(CustomGenre).filter(CustomGenre.id == genre_id).first()
    if not genre:
        raise HTTPException(status_code=404, detail="Genre not found")
    if genre.is_system:
        raise HTTPException(status_code=400, detail="系统预设题材不可删除")
    db.delete(genre)
    db.commit()
    return {"status": "ok"}
