"""剧情点（PlotPoint）API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import PlotPoint, Project, Chapter
from typing import Optional


router = APIRouter(prefix="/api/projects/{project_id}/plot-points", tags=["剧情点"])


# ─── Schemas ───

class PlotPointCreate(BaseModel):
    title: str
    description: str = ""
    tags: list[str] = []
    importance: str = "major"             # major / minor
    status: str = "planning"              # planning / introduced / developing / climaxed / resolved / abandoned
    intro_chapter_id: int | None = None
    develop_chapter_id: int | None = None
    climax_chapter_id: int | None = None
    resolve_chapter_id: int | None = None
    intro_note: str = ""
    develop_note: str = ""
    climax_note: str = ""
    resolve_note: str = ""


class PlotPointUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    importance: str | None = None
    status: str | None = None
    intro_chapter_id: int | None = None
    develop_chapter_id: int | None = None
    climax_chapter_id: int | None = None
    resolve_chapter_id: int | None = None
    intro_note: str | None = None
    develop_note: str | None = None
    climax_note: str | None = None
    resolve_note: str | None = None


# ─── Routes ───

@router.get("")
async def list_plot_points(
    project_id: str,
    q: str | None = Query(None, description="搜索关键字（标题/描述/标签）"),
    status: str | None = Query(None, description="按状态筛选"),
    importance: str | None = Query(None, description="按重要性筛选（major/minor）"),
    chapter_range: str | None = Query(None, description="章节范围，格式 'min-max' 或单值"),
    db: Session = Depends(get_db),
):
    """获取剧情点列表（支持搜索 + 筛选）"""
    query = db.query(PlotPoint).filter(PlotPoint.project_id == project_id)
    if status:
        query = query.filter(PlotPoint.status == status)
    if importance:
        query = query.filter(PlotPoint.importance == importance)
    items = query.order_by(PlotPoint.importance.asc(), PlotPoint.created_at.asc()).all()

    # 全文搜索：标题 / 描述 / 标签 任一匹配（在内存里做，简单可靠）
    if q:
        ql = q.lower()
        items = [
            pp for pp in items
            if ql in (pp.title or '').lower()
            or ql in (pp.description or '').lower()
            or any(ql in (t or '').lower() for t in (pp.tags or []))
        ]

    # 章节范围筛选（在内存里做，因为需要 join chapter 取 order）
    if chapter_range:
        try:
            if '-' in chapter_range:
                lo, hi = chapter_range.split('-', 1)
                lo_i = int(lo) if lo else None
                hi_i = int(hi) if hi else None
            else:
                lo_i = hi_i = int(chapter_range)
        except ValueError:
            lo_i = hi_i = None
        if lo_i is not None or hi_i is not None:
            chapter_ids = {pp.id: set() for pp in items}
            for pp in items:
                for cid in [pp.intro_chapter_id, pp.develop_chapter_id, pp.climax_chapter_id, pp.resolve_chapter_id]:
                    if cid: chapter_ids[pp.id].add(cid)
            cid_to_order = {}
            all_cids = set()
            for s in chapter_ids.values(): all_cids.update(s)
            if all_cids:
                rows = db.query(Chapter).filter(Chapter.id.in_(all_cids)).all()
                for r in rows:
                    cid_to_order[r.id] = r.order + 1
            items = [
                pp for pp in items
                if any(
                    (lo_i is None or cid_to_order.get(cid, 0) >= lo_i) and
                    (hi_i is None or cid_to_order.get(cid, 0) <= hi_i)
                    for cid in chapter_ids[pp.id]
                )
            ]

    return items


@router.post("", status_code=201)
async def create_plot_point(project_id: str, data: PlotPointCreate, db: Session = Depends(get_db)):
    """创建剧情点"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    pp = PlotPoint(project_id=project_id, **data.model_dump())
    db.add(pp)
    db.commit()
    db.refresh(pp)
    return pp


@router.get("/{pp_id}")
async def get_plot_point(project_id: str, pp_id: int, db: Session = Depends(get_db)):
    pp = db.query(PlotPoint).filter(PlotPoint.id == pp_id, PlotPoint.project_id == project_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="PlotPoint not found")
    return pp


@router.put("/{pp_id}")
async def update_plot_point(project_id: str, pp_id: int, data: PlotPointUpdate, db: Session = Depends(get_db)):
    pp = db.query(PlotPoint).filter(PlotPoint.id == pp_id, PlotPoint.project_id == project_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="PlotPoint not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(pp, key, value)
    db.commit()
    db.refresh(pp)
    return pp


@router.delete("/{pp_id}")
async def delete_plot_point(project_id: str, pp_id: int, db: Session = Depends(get_db)):
    pp = db.query(PlotPoint).filter(PlotPoint.id == pp_id, PlotPoint.project_id == project_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="PlotPoint not found")
    db.delete(pp)
    db.commit()
    return {"status": "ok"}