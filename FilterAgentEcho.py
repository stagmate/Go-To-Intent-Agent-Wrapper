from models import (
    User, SessionState, ClarificationResponse, FinalResponse, ApiResponse
)
from core_logic import (
    llm_client,
    check_cross_department_query,
    disambiguate_metric
)

async def handle_clarification_response(answer: str, state: SessionState, user: User) -> ApiResponse:
   
    
    normalized_answer = answer.strip()
    
    if normalized_answer not in state.valid_options:
        
        return ClarificationResponse(
            type=state.pending_question,
            message=f"'{answer}' is not a valid selection. Please choose from the list.",
            options=state.valid_options,
            session_state=state  
        )
    
    if state.pending_question == "ASK_DEPARTMENT":
        active_department = normalized_answer
        
        
        if check_cross_department_query(
            state.original_query, active_department, user.accessible_departments
        ):
            result = llm_client.generate_complex(
                query=state.original_query, context="all_departments"
            )
            return FinalResponse(answer=result["answer"], debug_context=result["debug_context"])

        metric_result = disambiguate_metric(state.original_query, active_department)
        
        if metric_result["status"] == "NEEDS_CLARIFICATION":
            
            new_state = SessionState(
                original_query=state.original_query,
                pending_question="ASK_METRIC",
                valid_options=metric_result["options"],
                active_department=active_department
            )
            return ClarificationResponse(
                type="ASK_METRIC",
                message="Which of these metrics are you interested in?",
                options=metric_result["options"],
                session_state=new_state
            )
        
        
        active_metric = metric_result["metric"]
        result = llm_client.generate(
            query=state.original_query,
            context=active_department,
            metric=active_metric
        )
        return FinalResponse(answer=result["answer"], debug_context=result["debug_context"])

    elif state.pending_question == "ASK_METRIC":
        
        active_metric = normalized_answer
        active_department = state.active_department
        
        
        result = llm_client.generate(
            query=state.original_query,
            context=active_department,
            metric=active_metric
        )
        return FinalResponse(answer=result["answer"], debug_context=result["debug_context"])
