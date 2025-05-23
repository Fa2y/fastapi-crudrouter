import asyncio
from typing import Any, Callable, List, Type, cast, Coroutine, Optional, Union
from fastapi import Request
from . import CRUDGenerator, NOT_FOUND
from ._types import (
    PAGINATIONEXTRADATA,
    DEPENDENCIES,
    PAGINATION,
    PYDANTIC_SCHEMA as SCHEMA,
)

try:
    from tortoise.models import Model
except ImportError:
    Model = None  # type: ignore
    tortoise_installed = False
else:
    tortoise_installed = True


CALLABLE = Callable[..., Coroutine[Any, Any, Model]]
CALLABLE_LIST = Callable[..., Coroutine[Any, Any, PAGINATIONEXTRADATA | List[Model]]]


class TortoiseCRUDRouter(CRUDGenerator[SCHEMA]):
    def __init__(
        self,
        schema: Type[SCHEMA],
        db_model: Type[Model],
        create_schema: Optional[Type[SCHEMA]] = None,
        update_schema: Optional[Type[SCHEMA]] = None,
        prefix: Optional[str] = None,
        tags: Optional[List[str]] = None,
        paginate: Optional[int] = None,
        get_all_route: Union[bool, DEPENDENCIES] = True,
        get_one_route: Union[bool, DEPENDENCIES] = True,
        create_route: Union[bool, DEPENDENCIES] = True,
        update_route: Union[bool, DEPENDENCIES] = True,
        delete_one_route: Union[bool, DEPENDENCIES] = True,
        delete_all_route: Union[bool, DEPENDENCIES] = True,
        paginationextradata: Union[bool, DEPENDENCIES] = False,
        using_db: Optional[Any] = None,
        **kwargs: Any
    ) -> None:
        assert (
            tortoise_installed
        ), "Tortoise ORM must be installed to use the TortoiseCRUDRouter."

        self.db_model = db_model
        self._pk: str = db_model.describe()["pk_field"]["db_column"]
        self.paginationextradata = paginationextradata
        self.using_db = using_db

        super().__init__(
            schema=schema,
            create_schema=create_schema,
            update_schema=update_schema,
            prefix=prefix or db_model.describe()["name"].replace("None.", ""),
            tags=tags,
            paginate=paginate,
            get_all_route=get_all_route,
            get_one_route=get_one_route,
            create_route=create_route,
            update_route=update_route,
            delete_one_route=delete_one_route,
            delete_all_route=delete_all_route,
            **kwargs
        )

    def _get_all(self, *args: Any, **kwargs: Any) -> CALLABLE_LIST:
        async def route(
            request: Request,
            pagination: PAGINATION = self.pagination,
        ) -> PAGINATIONEXTRADATA | List[Model]:
            skip, limit, sortby = (
                pagination.get("skip"),
                pagination.get("limit"),
                pagination.get("sortby"),
            )
            using_db = (
                self.using_db
                if not callable(self.using_db)
                else self.using_db(**request.path_params)
            )
            if asyncio.coroutines.iscoroutine(using_db):
                using_db = await using_db
            if sortby:
                query = (
                    self.db_model.all(using_db=using_db)
                    .order_by(sortby)
                    .offset(cast(int, skip))
                )
            else:
                query = self.db_model.all(using_db=using_db).offset(cast(int, skip))
            if self.paginationextradata:
                count = self.db_model.all(
                    using_db=using_db
                ).count()  # added for issue #138
            if limit:
                query = query.limit(limit)
            query = self.schema.from_queryset(query)  # added from issue #153
            if self.paginationextradata:
                return {"results": await query, "count": await count}
            return await query

        return route

    def _get_one(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(request: Request, item_id: int) -> Model:
            using_db = (
                self.using_db
                if not callable(self.using_db)
                else self.using_db(**request.path_params)
            )
            if asyncio.coroutines.iscoroutine(using_db):
                using_db = await using_db
            model = await self.db_model.filter(id=item_id).using_db(using_db).first()
            if model:
                model = await self.schema.from_tortoise_orm(
                    model
                )  # added from issue #153
                if model:
                    return model
                else:
                    raise NOT_FOUND
            else:
                raise NOT_FOUND

        return route

    def _create(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(request: Request, model: self.create_schema) -> Model:  # type: ignore
            using_db = (
                self.using_db
                if not callable(self.using_db)
                else self.using_db(**request.path_params)
            )
            if asyncio.coroutines.iscoroutine(using_db):
                using_db = await using_db
            db_model = self.db_model(**model.dict())
            await db_model.save(using_db=using_db)

            return await self.schema.from_tortoise_orm(db_model)

        return route

    def _update(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(
            item_id: int,
            model: self.update_schema,
            request: Request,  # type: ignore
        ) -> Model:
            using_db = (
                self.using_db
                if not callable(self.using_db)
                else self.using_db(**request.path_params)
            )
            if asyncio.coroutines.iscoroutine(using_db):
                using_db = await using_db
            await self.db_model.filter(id=item_id).using_db(using_db).update(
                **model.dict(exclude_unset=True)
            )
            return await self._get_one()(item_id=item_id, request=request)

        return route

    def _delete_all(self, *args: Any, **kwargs: Any) -> CALLABLE_LIST:
        async def route(request: Request) -> List[Model]:
            using_db = (
                self.using_db
                if not callable(self.using_db)
                else self.using_db(**request.path_params)
            )
            if asyncio.coroutines.iscoroutine(using_db):
                using_db = await using_db
            await self.db_model.all(using_db=using_db).delete(using_db=using_db)
            return await self._get_all()(pagination={"skip": 0, "limit": None})

        return route

    def _delete_one(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(request: Request, item_id: int) -> Model:
            using_db = (
                self.using_db
                if not callable(self.using_db)
                else self.using_db(**request.path_params)
            )
            if asyncio.coroutines.iscoroutine(using_db):
                using_db = await using_db
            model: Model = await self._get_one()(item_id=item_id, request=request)
            await self.db_model.filter(id=item_id).using_db(using_db).delete()

            return model

        return route
