"""导出正文 API"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Chapter, Project
from logger import logger
import re
from urllib.parse import quote
import zipfile
import io


router = APIRouter(prefix="/api/export", tags=["导出"])


class ExportRequest(BaseModel):
    project_id: int
    chapter_ids: list[int]
    rechapter: bool = False
    words_per_chapter: int = 3000  # 重新分章时每章字数
    format: str = "txt"  # txt 或 markdown
    save_individual: bool = False  # 章节独立保存（每章一个文件，打包zip）


def split_text_by_paragraphs(text: str, target_words: int, tolerance: float = 0.1) -> list[str]:
    """
    按段落边界分割文本，保证段落完整，字数偏差≤10%
    
    Args:
        text: 原始文本
        target_words: 目标每章字数
        tolerance: 容差比例（默认10%）
    
    Returns:
        分割后的章节列表
    """
    # 按段落分割（以换行符分隔）
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    
    if not paragraphs:
        return [text] if text.strip() else []
    
    min_words = int(target_words * (1 - tolerance))
    max_words = int(target_words * (1 + tolerance))
    
    chapters = []
    current_chapter = []
    current_words = 0
    
    for para in paragraphs:
        para_words = len(para)
        
        # 如果当前段落加入后超出上限，且当前已有内容，则保存当前章节
        if current_words + para_words > max_words and current_chapter:
            chapters.append('\n\n'.join(current_chapter))
            current_chapter = []
            current_words = 0
        
        current_chapter.append(para)
        current_words += para_words
    
    # 保存最后一章
    if current_chapter:
        chapters.append('\n\n'.join(current_chapter))
    
    return chapters if chapters else [text]


def format_as_txt(chapters: list[dict]) -> str:
    """格式化为TXT"""
    lines = []
    for ch in chapters:
        lines.append(f"第{ch['order']}章 {ch['title']}")
        lines.append("=" * 40)
        lines.append(ch['content'])
        lines.append("")  # 空行分隔
    return '\n'.join(lines)


def format_as_markdown(chapters: list[dict]) -> str:
    """格式化为Markdown"""
    lines = []
    for ch in chapters:
        lines.append(f"## 第{ch['order']}章 {ch['title']}")
        lines.append("")
        lines.append(ch['content'])
        lines.append("")
        lines.append("---")
        lines.append("")
    return '\n'.join(lines)


@router.post("/chapters")
async def export_chapters(req: ExportRequest, db: Session = Depends(get_db)):
    """
    导出章节正文
    
    Returns:
        文件内容和文件名
    """
    # 获取章节
    chapters = db.query(Chapter).filter(
        Chapter.id.in_(req.chapter_ids),
        Chapter.project_id == req.project_id,
    ).order_by(Chapter.order).all()
    
    if not chapters:
        raise HTTPException(status_code=404, detail="未找到选中的章节")
    
    # 获取项目名称
    project = db.query(Project).filter(Project.id == req.project_id).first()
    project_name = project.title if project else "未命名项目"
    
    # 准备章节数据
    chapter_data = []
    for ch in chapters:
        chapter_data.append({
            'order': ch.order + 1,  # 转为1-based
            'title': ch.title,
            'content': ch.content or '',
        })
    
    # 重新分章
    if req.rechapter:
        # 合并所有章节内容
        all_content = '\n\n'.join([
            f"第{ch['order']}章 {ch['title']}\n{ch['content']}" 
            for ch in chapter_data
        ])
        
        # 按段落边界分割
        split_texts = split_text_by_paragraphs(all_content, req.words_per_chapter)
        
        # 重新组织为章节
        chapter_data = []
        for i, text in enumerate(split_texts):
            # 尝试从分割后的文本中提取原章节标题
            title_match = re.match(r'第\d+章\s*(.+?)\n', text)
            title = title_match.group(1) if title_match else f"第{i+1}章"
            
            # 如果标题包含原文内容，只取标题部分
            if len(title) > 50:
                title = f"第{i+1}章"
            
            chapter_data.append({
                'order': i + 1,
                'title': title,
                'content': text,
            })
    
    # 格式化
    if req.format == "markdown":
        ext = ".md"
    else:
        ext = ".txt"
    
    # 章节独立保存 → 打包为 zip
    if req.save_individual:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for ch in chapter_data:
                order_str = str(ch['order']).zfill(3)
                # 清理文件名中的非法字符
                safe_title = re.sub(r'[\\/:*?"<>|]', '_', ch['title'])
                fname = f"{order_str}_{safe_title}{ext}"
                
                if req.format == "markdown":
                    file_content = f"# 第{ch['order']}章 {ch['title']}\n\n{ch['content']}"
                else:
                    file_content = f"第{ch['order']}章 {ch['title']}\n{'='*40}\n{ch['content']}"
                
                zf.writestr(fname, file_content.encode('utf-8'))
        
        buf.seek(0)
        zip_filename = f"{project_name}_分章导出.zip"
        encoded_zip = quote(zip_filename)
        return Response(
            content=buf.read(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_zip}",
            }
        )
    
    # 单文件导出
    if req.format == "markdown":
        content = format_as_markdown(chapter_data)
        filename = f"{project_name}.md"
        media_type = "text/markdown; charset=utf-8"
    else:
        content = format_as_txt(chapter_data)
        filename = f"{project_name}.txt"
        media_type = "text/plain; charset=utf-8"
    
    # 返回文件供浏览器下载
    encoded_filename = quote(filename)
    return Response(
        content=content.encode('utf-8'),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        }
    )
