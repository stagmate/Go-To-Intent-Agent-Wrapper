import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Union
import nest_asyncio

nest_asyncio.apply()

app = FastAPI(
    title="Gojek Intent Agent",
    description="Implements the multi-stage intent pipeline."
)

class UserQueryRequest(BaseModel):
    query: str
    auth_token: str = Field(..., example="user_kushagra_token")

class ClarificationResponse(BaseModel):
    status: Literal["NEEDS_CLARIFICATION"] = "NEEDS_CLARIFICATION"
    type: Literal["ASK_DEPARTMENT", "ASK_METRIC"]
    message: str
    options: List[str]

class FinalResponse(BaseModel):
    status: Literal["SUCCESS"] = "SUCCESS"
    answer: str
    debug_context: dict

class ErrorResponse(BaseModel):
    status: Literal["ERROR"] = "ERROR"
    message: str

ApiResponse = Union[ClarificationResponse, FinalResponse, ErrorResponse]

class User(BaseModel):
    user_id: str
    accessible_departments: List[str]

def get_user_from_token(token: str) -> User:
    if token == "user_kushagra_token":
        return User(
            user_id="kushagra.kumar",
            accessible_departments=["Food", "Merchant", "Transport"]
        )
    if token == "user_simple_token":
        return User(
            user_id="simple.user",
            accessible_departments=["Food"]
        )
    return None

class MockLLM:
    def generate(self, query: str, context: str, metric: str = None) -> str:
        sql = f"SELECT {metric or 'COUNT(*)'} FROM {context.lower()}_table WHERE ..."
        answer = f"Based on your query for '{metric}' in '{context}', here is the result."
        
        return {
            "answer": answer,
            "sql_query": sql,
            "debug_context": {
                "final_query": query,
                "final_context": context,
                "final_metric": metric
            }
        }
    
    def generate_complex(self, query: str, context: str) -> str:
        sql = "SELECT ... FROM food_table JOIN merchant_table ON ..."
        answer = "This is a complex cross-department answer."
        return {
            "answer": answer,
            "sql_query": sql,
            "debug_context": {
                "final_query": query,
                "final_context": context,
                "final_metric": None
            }
        }

llm_client = MockLLM()

def disambiguate_department(query: str, departments: List[str]) -> dict:
    query_low = query.lower()
    
    if len(departments) == 1:
        return {"status": "SUCCESS", "department": departments[0]}

    inferred_dept = None
    if "food" in query_low or "order" in query_low:
        inferred_dept = "Food"
    elif "merchant" in query_low or "restaurant" in query_low:
        inferred_dept = "Merchant"
    elif "transport" in query_low or "driver" in query_low:
        inferred_dept = "Transport"
    
    if inferred_dept and inferred_dept in departments:
        return {"status": "SUCCESS", "department": inferred_dept}

    return {
        "status": "NEEDS_CLARIFICATION",
        "options": departments
    }

def check_cross_department_query(query: str, active_dept: str, all_depts: List[str]) -> bool:
    query_low = query.lower()
    
    if "compare" in query_low:
        return True
        
    other_depts = [d for d in all_depts if d != active_dept]
    for dept in other_depts:
        if dept.lower() in query_low:
            return True
            
    return False

def disambiguate_metric(query: str, active_dept: str) -> dict:
    query_low = query.lower()

    if "sales" in query_low:
        return {
            "status": "NEEDS_CLARIFICATION",
            "options": ["gross_sales", "net_sales"]
        }
    
    if "order count" in query_low:
        return {"status": "SUCCESS", "metric": "order_count"}
    if "avg delivery time" in query_low:
        return {"status": "SUCCESS", "metric": "avg_delivery_time"}
    
    return {"status": "SUCCESS", "metric": "inferred_from_query"}

@app.post("/query", response_model=ApiResponse)
async def handle_user_query(request: UserQueryRequest):
    
    user = get_user_from_token(request.auth_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    dept_result = disambiguate_department(request.query, user.accessible_departments)
    
    if dept_result["status"] == "NEEDS_CLARIFICATION":
        return ClarificationResponse(
            type="ASK_DEPARTMENT",
            message="① For which dept would you like to see the info?",
            options=dept_result["options"]
        )
    
    active_department = dept_result["department"]
    
    is_complex = check_cross_department_query(
        request.query, active_department, user.accessible_departments
    )
    
    if is_complex:
        result = llm_client.generate_complex(
            query=request.query,
            context="all_departments"
        )
        return FinalResponse(answer=result["answer"], debug_context=result["debug_context"])

    metric_result = disambiguate_metric(request.query, active_department)
    
    if metric_result["status"] == "NEEDS_CLARIFICATION":
        return ClarificationResponse(
            type="ASK_METRIC",
            message="② Which of these metrics are you interested in?",
            options=metric_result["options"]
        )

    active_metric = metric_result["metric"]

    result = llm_client.generate(
        query=request.query,
        context=active_department,
        metric=active_metric
    )
    return FinalResponse(answer=result["answer"], debug_context=result["debug_context"])

if __name__ != "__main__":
    print("Starting Uvicorn server... (This will block this cell)")
    uvicorn.run(app, host="127.0.0.1", port=8000)
