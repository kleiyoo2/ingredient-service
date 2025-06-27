from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import date
import httpx
from database import get_db_connection
import logging

# config
logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="https://bleu-ums.onrender.com/auth/token")
router = APIRouter(prefix="/ingredients", tags=["ingredients"])

# helper functions
def row_to_dict(row: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Converts a pyodbc.Row object to a dictionary."""
    if row is None:
        return None
    return dict(zip([column[0] for column in row.cursor_description], row))

# threshold for stock status
thresholds = {
    "g": 50, "kg": 0.5, "ml": 100, "l": 0.5,
}

def get_status(amount: float, measurement: str):
    meas_lower = (measurement or "").lower()
    if amount <= 0: return "Not Available"
    if amount <= thresholds.get(meas_lower, 1): return "Low Stock"
    return "Available"

class IngredientCreate(BaseModel):
    IngredientName: str
    Amount: float
    Measurement: str
    BestBeforeDate: date
    ExpirationDate: date

class IngredientUpdate(BaseModel):
    IngredientName: str
    Amount: float
    Measurement: str
    BestBeforeDate: date
    ExpirationDate: date

class IngredientOut(BaseModel):
    IngredientID: int
    IngredientName: str
    Amount: float
    Measurement: str
    BestBeforeDate: date
    ExpirationDate: date
    Status: str

# models for the deduction endpoint
class SoldItem(BaseModel):
    name: str = Field(..., alias="name")
    quantity: int = Field(..., gt=0)
  

class DeductSaleRequest(BaseModel):
    cartItems: List[SoldItem]

# auth validation
async def validate_token_and_roles(token: str, allowed_roles: List[str]):
    USER_SERVICE_ME_URL = "https://bleu-ums.onrender.com/auth/users/me"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(USER_SERVICE_ME_URL, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            error_detail = f"Ingredients Auth service error: {e.response.status_code} - {e.response.text}"
            logger.error(error_detail)
            raise HTTPException(status_code=e.response.status_code, detail=error_detail)
        except httpx.RequestError as e:
            logger.error(f"Ingredients Auth service unavailable: {e}")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Ingredients Auth service unavailable: {e}")

    user_data = response.json()
    user_role = user_data.get("userRole")
    if user_role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

# get ingredients
@router.get("/", response_model=List[IngredientOut])
async def get_all_ingredients(token: str = Depends(oauth2_scheme)):
    await validate_token_and_roles(token, ["admin", "manager", "staff", "cashier"])
    conn = None
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT IngredientID, IngredientName, Amount, Measurement, BestBeforeDate, ExpirationDate, Status FROM Ingredients")
            rows = await cursor.fetchall()
            return [IngredientOut(**row_to_dict(row)) for row in rows]
    finally:
        if conn: await conn.close()

# create ingredients
@router.post("/", response_model=IngredientOut, status_code=status.HTTP_201_CREATED)
async def add_ingredient(ingredient: IngredientCreate, token: str = Depends(oauth2_scheme)):
    await validate_token_and_roles(token, ["admin", "manager", "staff"])
    conn = None
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1 FROM Ingredients WHERE IngredientName COLLATE Latin1_General_CI_AS = ?", ingredient.IngredientName)
            if await cursor.fetchone():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ingredient name already exists.")

            status_val = get_status(ingredient.Amount, ingredient.Measurement)
            
            await cursor.execute("""
                INSERT INTO Ingredients (IngredientName, Amount, Measurement, BestBeforeDate, ExpirationDate, Status)
                OUTPUT INSERTED.IngredientID, INSERTED.IngredientName, INSERTED.Amount, INSERTED.Measurement, 
                       INSERTED.BestBeforeDate, INSERTED.ExpirationDate, INSERTED.Status
                VALUES (?, ?, ?, ?, ?, ?)
            """, ingredient.IngredientName, ingredient.Amount, ingredient.Measurement,
                ingredient.BestBeforeDate, ingredient.ExpirationDate, status_val)
            
            row = await cursor.fetchone()
            await conn.commit()
            return IngredientOut(**row_to_dict(row))
    finally:
        if conn: await conn.close()

# update ingredients
@router.put("/{ingredient_id}", response_model=IngredientOut)
async def update_ingredient(ingredient_id: int, ingredient: IngredientUpdate, token: str = Depends(oauth2_scheme)):
    await validate_token_and_roles(token, ["admin", "manager", "staff"])
    conn = None
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1 FROM Ingredients WHERE IngredientName COLLATE Latin1_General_CI_AS = ? AND IngredientID != ?",
                                 ingredient.IngredientName, ingredient_id)
            if await cursor.fetchone():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ingredient name already exists.")
            
            status_val = get_status(ingredient.Amount, ingredient.Measurement)
            
            await cursor.execute("""
                UPDATE Ingredients SET IngredientName = ?, Amount = ?, Measurement = ?,
                BestBeforeDate = ?, ExpirationDate = ?, Status = ?
                WHERE IngredientID = ?
            """, ingredient.IngredientName, ingredient.Amount, ingredient.Measurement,
                ingredient.BestBeforeDate, ingredient.ExpirationDate, status_val, ingredient_id)
            
            await cursor.execute("""
                SELECT IngredientID, IngredientName, Amount, Measurement, 
                       BestBeforeDate, ExpirationDate, Status 
                FROM Ingredients WHERE IngredientID = ?
            """, ingredient_id)
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found")

            await conn.commit()
            return IngredientOut(**row_to_dict(row))
    finally:
        if conn: await conn.close()

# delete ingredients
@router.delete("/{ingredient_id}", status_code=status.HTTP_200_OK)
async def delete_ingredient(ingredient_id: int, token: str = Depends(oauth2_scheme)):
    await validate_token_and_roles(token, ["admin", "manager", "staff"])
    conn = None
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            delete_op = await cursor.execute("DELETE FROM Ingredients WHERE IngredientID = ?", ingredient_id)
            if delete_op.rowcount == 0:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingredient not found")
            await conn.commit()
        return {"message": "Ingredient deleted successfully"}
    finally:
        if conn: await conn.close()
        
# get ingredient count
@router.get("/count")
async def get_ingredient_count(token: str = Depends(oauth2_scheme)):
    await validate_token_and_roles(token, ["admin", "manager", "staff", "cashier"])
    conn = None
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) as count FROM Ingredients")
            row = await cursor.fetchone()
            return {"count": row.count if row else 0}
    finally:
        if conn: await conn.close()

# get stock status counts
@router.get("/stock-status-counts")
async def get_stock_status_counts(token: str = Depends(oauth2_scheme)):
    await validate_token_and_roles(token, ["admin", "manager", "staff", "cashier"])
    conn = None
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT
                    SUM(CASE WHEN Status = 'Available' THEN 1 ELSE 0 END) AS available_count,
                    SUM(CASE WHEN Status = 'Low Stock' THEN 1 ELSE 0 END) AS low_stock_count,
                    SUM(CASE WHEN Status = 'Not Available' THEN 1 ELSE 0 END) AS not_available_count
                FROM Ingredients
            """)
            row = await cursor.fetchone()
            return {
                "available": row.available_count or 0,
                "low_stock": row.low_stock_count or 0,
                "not_available": row.not_available_count or 0
            }
    finally:
        if conn: await conn.close()

# get low stock alerts
@router.get("/low-stock-alerts")
async def get_low_stock_alerts(token: str = Depends(oauth2_scheme)):
    await validate_token_and_roles(token, ["admin", "manager", "staff", "cashier"])
    conn = None
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT IngredientName as name, 'Ingredient' as category, Amount as inStock, 
                       5 as reorderLevel, NULL as lastRestocked, Status as status
                FROM Ingredients
                WHERE Status = 'Low Stock'
            """)
            rows = await cursor.fetchall()
            return [dict(zip([column[0] for column in row.cursor_description], row)) for row in rows]
    finally:
        if conn: await conn.close()

# deduct from pos
@router.post("/deduct-from-sale", status_code=status.HTTP_200_OK)
async def deduct_ingredients_from_sale(
    sale_data: DeductSaleRequest, 
    token: str = Depends(oauth2_scheme)
):
    """
    Receives a list of sold products and deducts the required ingredients
    from inventory based on their recipes.
    This should be called by the Sales Service after a transaction is confirmed.
    """
    await validate_token_and_roles(token, ["admin", "cashier", "manager"])
    
    conn = None
    try:
        conn = await get_db_connection()
        
        async with conn.cursor() as cursor:
            
            for item in sale_data.cartItems:
                # find the recipe for the sold product
                await cursor.execute("""
                    SELECT r.RecipeID 
                    FROM Recipes r
                    JOIN Products p ON r.ProductID = p.ProductID
                    WHERE p.ProductName = ?
                """, item.name)
                recipe_row = await cursor.fetchone()
                
                # if a product has no recipe, skip it
                if not recipe_row:
                    logger.info(f"No recipe found for product '{item.name}'. Skipping deduction.")
                    continue
                
                recipe_id = recipe_row.RecipeID
                
                # get all ingredients required for the recipe
                await cursor.execute("""
                    SELECT IngredientID, Amount, Measurement 
                    FROM RecipeIngredients 
                    WHERE RecipeID = ?
                """, recipe_id)
                recipe_ingredients = await cursor.fetchall()
                
                # loop through each ingredient in the recipe and deduct from stock
                for recipe_ingredient in recipe_ingredients:
                    total_to_deduct = recipe_ingredient.Amount * item.quantity
                    
                    # deduct
                    await cursor.execute("""
                        UPDATE Ingredients
                        SET Amount = Amount - ?
                        WHERE IngredientID = ?
                    """, total_to_deduct, recipe_ingredient.IngredientID)
                    
                    logger.info(f"Deducted {total_to_deduct} {recipe_ingredient.Measurement} of IngredientID {recipe_ingredient.IngredientID} for sale of {item.quantity}x {item.name}")
            
            # after all deductions, update the status of all ingredients at once
            await cursor.execute("""
                UPDATE Ingredients
                SET Status = CASE
                    WHEN Amount <= 0 THEN 'Not Available'
                    WHEN (Measurement = 'g' AND Amount <= 50) OR
                         (Measurement = 'kg' AND Amount <= 0.5) OR
                         (Measurement = 'ml' AND Amount <= 100) OR
                         (Measurement = 'l' AND Amount <= 0.5) OR
                         (Measurement NOT IN ('g', 'kg', 'ml', 'l') AND Amount <= 1)
                    THEN 'Low Stock'
                    ELSE 'Available'
                END
            """)
            
            await conn.commit()
            
            return {"message": "Inventory deducted successfully."}

    except Exception as e:
        if conn:
            await conn.rollback()
        logger.error(f"Failed to deduct ingredients from sale. Transaction rolled back. Error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update inventory.")
    finally:
        if conn:
            await conn.close()