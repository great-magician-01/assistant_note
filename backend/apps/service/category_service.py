"""Category business logic: CRUD and tree assembly."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.category import Category
from backend.apps.utils.exceptions import BusinessError, NotFoundError


async def list_categories(
    db: AsyncSession,
    user_id: int,
) -> list[dict]:
    """Get all non-deleted categories for a user and assemble into tree."""
    result = await db.execute(
        select(Category)
        .where(Category.user_id == user_id, Category.is_deleted == 0)
        .order_by(Category.category_sort.asc(), Category.category_id.asc())
    )
    categories = result.scalars().all()

    # Build tree
    node_map: dict[int, dict] = {}
    roots: list[dict] = []

    for cat in categories:
        node = _category_to_dict(cat)
        node["children"] = []
        node_map[cat.category_id] = node

    for cat in categories:
        node = node_map[cat.category_id]
        if cat.parent_id is None or cat.parent_id not in node_map:
            roots.append(node)
        else:
            node_map[cat.parent_id]["children"].append(node)

    return roots


async def create_category(
    db: AsyncSession,
    user_id: int,
    category_name: str,
    category_icon: Optional[str] = None,
    category_sort: int = 0,
    parent_id: Optional[int] = None,
) -> Category:
    """Create a new category.

    Raises NotFoundError if the parent does not exist, BusinessError on name conflict.
    """
    # Validate parent exists and belongs to user
    if parent_id is not None:
        result = await db.execute(
            select(Category).where(
                Category.category_id == parent_id,
                Category.user_id == user_id,
                Category.is_deleted == 0,
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("父分类不存在")

    # Check duplicate name under same parent
    result = await db.execute(
        select(Category).where(
            Category.user_id == user_id,
            Category.category_name == category_name,
            Category.parent_id == parent_id,
            Category.is_deleted == 0,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise BusinessError("同一父分类下已存在同名分类")

    category = Category(
        user_id=user_id,
        category_name=category_name,
        category_icon=category_icon,
        category_sort=category_sort,
        parent_id=parent_id,
    )
    db.add(category)
    await db.flush()
    return category


async def update_category(
    db: AsyncSession,
    user_id: int,
    category_id: int,
    fields: dict[str, Any],
) -> Category:
    """Update a category with only the provided fields.

    ``fields`` contains only keys the client actually sent (built via
    ``model_dump(exclude_unset=True)``), so a key present with value ``None``
    means "set to NULL", while an absent key means "leave unchanged".

    Raises NotFoundError if the category/parent does not exist,
    BusinessError on name conflict or invalid move.
    """
    result = await db.execute(
        select(Category).where(
            Category.category_id == category_id,
            Category.user_id == user_id,
            Category.is_deleted == 0,
        )
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise NotFoundError("分类不存在")

    # Determine the effective parent (new one if being changed, else current)
    effective_parent = fields.get("parent_id", category.parent_id) if "parent_id" in fields else category.parent_id

    # Name change → check duplicate under the effective parent
    if "category_name" in fields:
        new_name = fields["category_name"]
        dup_result = await db.execute(
            select(Category).where(
                Category.user_id == user_id,
                Category.category_name == new_name,
                Category.parent_id == effective_parent,
                Category.is_deleted == 0,
                Category.category_id != category_id,
            )
        )
        if dup_result.scalar_one_or_none() is not None:
            raise BusinessError("同一父分类下已存在同名分类")
        category.category_name = new_name

    if "category_icon" in fields:
        category.category_icon = fields["category_icon"]

    if "category_sort" in fields:
        category.category_sort = fields["category_sort"]

    if "parent_id" in fields:
        new_parent = fields["parent_id"]
        if new_parent is not None:
            if new_parent == category_id:
                raise BusinessError("不能将自己设为父分类")
            result = await db.execute(
                select(Category).where(
                    Category.category_id == new_parent,
                    Category.user_id == user_id,
                    Category.is_deleted == 0,
                )
            )
            if result.scalar_one_or_none() is None:
                raise NotFoundError("父分类不存在")
            # Prevent circular reference: new parent must not be a descendant
            if await _is_descendant(db, user_id, category_id, new_parent):
                raise BusinessError("不能将分类移动到自己的子分类下")
        category.parent_id = new_parent

    await db.flush()
    return category


async def delete_category(
    db: AsyncSession,
    user_id: int,
    category_id: int,
) -> None:
    """Soft delete a category and all its descendants."""
    result = await db.execute(
        select(Category).where(
            Category.category_id == category_id,
            Category.user_id == user_id,
            Category.is_deleted == 0,
        )
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise NotFoundError("分类不存在")

    # Collect all descendant IDs
    all_ids = await _get_descendant_ids(db, user_id, category_id)
    all_ids.add(category_id)

    # Soft delete all
    for cid in all_ids:
        r = await db.execute(
            select(Category).where(Category.category_id == cid)
        )
        cat = r.scalar_one_or_none()
        if cat is not None:
            cat.is_deleted = 1

    await db.flush()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _category_to_dict(cat: Category) -> dict:
    return {
        "category_id": cat.category_id,
        "user_id": cat.user_id,
        "category_name": cat.category_name,
        "category_icon": cat.category_icon,
        "category_sort": cat.category_sort,
        "parent_id": cat.parent_id,
        "created_at": cat.created_at.isoformat() if cat.created_at else None,
        "updated_at": cat.updated_at.isoformat() if cat.updated_at else None,
    }


async def _get_descendant_ids(
    db: AsyncSession, user_id: int, parent_id: int
) -> set[int]:
    """Recursively collect all descendant category IDs."""
    result = await db.execute(
        select(Category.category_id).where(
            Category.parent_id == parent_id,
            Category.user_id == user_id,
            Category.is_deleted == 0,
        )
    )
    child_ids = set(result.scalars().all())
    all_ids = set(child_ids)
    for cid in child_ids:
        all_ids |= await _get_descendant_ids(db, user_id, cid)
    return all_ids


async def _is_descendant(
    db: AsyncSession, user_id: int, ancestor_id: int, target_id: int
) -> bool:
    """Check if target_id is a descendant of ancestor_id."""
    descendants = await _get_descendant_ids(db, user_id, ancestor_id)
    return target_id in descendants
