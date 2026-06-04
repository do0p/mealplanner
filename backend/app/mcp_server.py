"""MCP server exposing mealplanner recipes and plans as tools."""
import json
import logging

from mcp.server import Server
from mcp.types import TextContent, Tool
from sqlmodel import Session

from app.db import engine, init_db
from app.models import EntryWrite, IngredientWrite, PlanCreate, PlanUpdate, RecipeCreate
from app.services import plan_service, recipe_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()

server = Server("mealplanner")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_recipes",
            description=(
                "List all accepted recipes. Optional filters: course "
                "(breakfast/appetizer/soup/salad/main/side/dessert/snack/beverage), "
                "is_vegetarian, is_vegan, is_favourite."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "course": {"type": "string"},
                    "is_vegetarian": {"type": "boolean"},
                    "is_vegan": {"type": "boolean"},
                    "is_favourite": {"type": "boolean"},
                },
            },
        ),
        Tool(
            name="get_recipe",
            description="Get full details of a recipe including ingredients and instruction steps.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "integer"},
                },
                "required": ["recipe_id"],
            },
        ),
        Tool(
            name="create_recipe",
            description=(
                "Create a new recipe directly (without PDF import). "
                "Ingredient quantities must be normalised per 1 person."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "base_servings": {"type": "integer"},
                    "notes": {"type": "string"},
                    "course": {"type": "string"},
                    "calories_per_person": {"type": "number"},
                    "protein_per_person": {"type": "number"},
                    "fat_per_person": {"type": "number"},
                    "carbs_per_person": {"type": "number"},
                    "is_vegetarian": {"type": "boolean"},
                    "is_vegan": {"type": "boolean"},
                    "is_favourite": {"type": "boolean"},
                    "is_want_to_try": {"type": "boolean"},
                    "ingredients": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "quantity_per_person": {"type": "number"},
                                "unit": {"type": "string", "description": "g, ml, pcs, or null"},
                                "category": {"type": "string"},
                                "raw_text": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                    },
                    "steps": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="list_plans",
            description="List all meal plans with their entry counts.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_plan",
            description="Get a meal plan with all its recipe entries (slot, recipe title, people count).",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {"type": "integer"},
                },
                "required": ["plan_id"],
            },
        ),
        Tool(
            name="create_plan",
            description="Create a new weekly meal plan, optionally pre-populated with recipe entries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "recipe_id": {"type": "integer"},
                                "day": {"type": "string", "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]},
                                "meal": {"type": "string", "enum": ["Breakfast", "Lunch", "Dinner"]},
                                "people": {"type": "integer"},
                            },
                            "required": ["recipe_id", "day", "meal"],
                        },
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="update_plan",
            description=(
                "Update a meal plan's name or replace its entries entirely. "
                "Passing entries replaces ALL existing entries for the plan."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "recipe_id": {"type": "integer"},
                                "day": {"type": "string", "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]},
                                "meal": {"type": "string", "enum": ["Breakfast", "Lunch", "Dinner"]},
                                "people": {"type": "integer"},
                            },
                            "required": ["recipe_id", "day", "meal"],
                        },
                    },
                },
                "required": ["plan_id"],
            },
        ),
        Tool(
            name="get_shopping_list",
            description=(
                "Generate a shopping list for a meal plan, grouped by ingredient category. "
                "Ingredients are scaled per the people count on each plan entry, "
                "converted to metric units, and aggregated across all recipes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {"type": "integer"},
                },
                "required": ["plan_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.exception("Error in tool %s: %s", name, e)
        return [TextContent(type="text", text=f"Error: {e}")]


async def _dispatch(name: str, arguments: dict) -> str:
    if name == "list_recipes":
        with Session(engine) as session:
            recipes = recipe_service.list_recipes(session, status="accepted")
        course = arguments.get("course")
        if course is not None:
            recipes = [r for r in recipes if r.course and r.course.lower() == course.lower()]
        is_veg = arguments.get("is_vegetarian")
        if is_veg is not None:
            recipes = [r for r in recipes if r.is_vegetarian == is_veg]
        is_vegan = arguments.get("is_vegan")
        if is_vegan is not None:
            recipes = [r for r in recipes if r.is_vegan == is_vegan]
        is_fav = arguments.get("is_favourite")
        if is_fav is not None:
            recipes = [r for r in recipes if r.is_favourite == is_fav]
        return json.dumps([r.model_dump(mode="json") for r in recipes], ensure_ascii=False)

    if name == "get_recipe":
        with Session(engine) as session:
            recipe = recipe_service.get_recipe(session, arguments["recipe_id"])
        if recipe is None:
            return json.dumps({"error": f"Recipe {arguments['recipe_id']} not found"})
        return json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False)

    if name == "create_recipe":
        ingredients = [
            IngredientWrite(
                name=i["name"],
                quantity_per_person=i.get("quantity_per_person"),
                unit=i.get("unit"),
                category=i.get("category"),
                raw_text=i.get("raw_text"),
            )
            for i in arguments.get("ingredients", [])
        ]
        data = RecipeCreate(
            title=arguments["title"],
            base_servings=arguments.get("base_servings"),
            notes=arguments.get("notes"),
            course=arguments.get("course"),
            calories_per_person=arguments.get("calories_per_person"),
            protein_per_person=arguments.get("protein_per_person"),
            fat_per_person=arguments.get("fat_per_person"),
            carbs_per_person=arguments.get("carbs_per_person"),
            is_vegetarian=arguments.get("is_vegetarian", False),
            is_vegan=arguments.get("is_vegan", False),
            is_favourite=arguments.get("is_favourite", False),
            is_want_to_try=arguments.get("is_want_to_try", False),
            ingredients=ingredients,
            steps=arguments.get("steps", []),
        )
        with Session(engine) as session:
            recipe = recipe_service.create_recipe(session, data)
        return json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False)

    if name == "list_plans":
        with Session(engine) as session:
            plans = plan_service.list_plans(session)
        return json.dumps([p.model_dump(mode="json") for p in plans], ensure_ascii=False)

    if name == "get_plan":
        with Session(engine) as session:
            plan = plan_service.get_plan(session, arguments["plan_id"])
        if plan is None:
            return json.dumps({"error": f"Plan {arguments['plan_id']} not found"})
        return json.dumps(plan.model_dump(mode="json"), ensure_ascii=False)

    if name == "create_plan":
        entries = [
            EntryWrite(
                recipe_id=e["recipe_id"],
                slot=f"{e['day']}-{e['meal']}",
                people=e.get("people", 2),
                sort_order=idx,
            )
            for idx, e in enumerate(arguments.get("entries", []))
        ]
        with Session(engine) as session:
            plan = plan_service.create_plan(session, PlanCreate(name=arguments["name"]))
            if entries:
                plan = plan_service.update_plan(session, plan.id, PlanUpdate(entries=entries))
        return json.dumps(plan.model_dump(mode="json"), ensure_ascii=False)

    if name == "update_plan":
        parsed_entries = None
        if "entries" in arguments:
            parsed_entries = [
                EntryWrite(
                    recipe_id=e["recipe_id"],
                    slot=f"{e['day']}-{e['meal']}",
                    people=e.get("people", 2),
                    sort_order=idx,
                )
                for idx, e in enumerate(arguments["entries"])
            ]
        with Session(engine) as session:
            plan = plan_service.update_plan(
                session,
                arguments["plan_id"],
                PlanUpdate(name=arguments.get("name"), entries=parsed_entries),
            )
        if plan is None:
            return json.dumps({"error": f"Plan {arguments['plan_id']} not found"})
        return json.dumps(plan.model_dump(mode="json"), ensure_ascii=False)

    if name == "get_shopping_list":
        with Session(engine) as session:
            shopping_list = plan_service.get_shopping_list(session, arguments["plan_id"])
        if shopping_list is None:
            return json.dumps({"error": f"Plan {arguments['plan_id']} not found"})
        return json.dumps(shopping_list.model_dump(mode="json"), ensure_ascii=False)

    return json.dumps({"error": f"Unknown tool: {name}"})
