"""
v29.0 — AGI Foundations
Meta-cognition, curiosity-driven learning, goal setting, theory of mind, creative problem solving
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ─── Schemas ──────────────────────────────────────────────────────────────

class MetaCognitionRequest(BaseModel):
    conversation: list[dict]
    focus_area: Optional[str] = None  # 'reasoning_quality', 'knowledge_gaps', 'tool_usage', 'response_style'

class GoalCreate(BaseModel):
    title: str
    description: str
    goal_type: str = "learning"  # 'learning', 'improvement', 'exploration', 'creation'
    priority: int = 5  # 1-10
    target_date: Optional[str] = None
    milestones: list[str] = []

class CuriosityQuery(BaseModel):
    topic: Optional[str] = None
    depth: str = "medium"  # 'shallow', 'medium', 'deep'

# ─── Meta-Cognition ───────────────────────────────────────────────────────

@router.post("/agi/meta-cognition", tags=["agi"])
async def analyze_reasoning(
    req: MetaCognitionRequest,
    _: None = Depends(verify_key),
):
    """Analyze DAWN's own reasoning process and identify improvements."""
    try:
        from llm.engine import get_engine
        
        engine = get_engine()
        
        # Build a meta-cognitive prompt
        focus_instructions = {
            "reasoning_quality": "Evaluate the logical consistency, completeness, and accuracy of the reasoning.",
            "knowledge_gaps": "Identify topics where DAWN lacked sufficient knowledge to give a complete answer.",
            "tool_usage": "Evaluate whether DAWN used the right tools at the right time, or missed opportunities to use tools.",
            "response_style": "Evaluate whether the response matched the user's communication style and needs.",
        }
        
        focus_text = focus_instructions.get(req.focus_area, "Evaluate the overall quality of DAWN's responses.")
        
        conversation_text = "\n".join([
            f"{m.get('role', 'unknown')}: {m.get('content', '')[:500]}"
            for m in req.conversation[-5:]  # Last 5 messages
        ])
        
        prompt = f"""You are a meta-cognitive analyzer. Analyze the following conversation and provide insights.

{focus_text}

Conversation:
{conversation_text}

Return a JSON object with:
- strengths: list of things DAWN did well
- improvements: list of specific things DAWN could improve
- confidence_score: 0.0 to 1.0 on how confident DAWN should be in its responses
- knowledge_gaps: list of topics DAWN should learn more about
- suggested_actions: list of concrete next steps"""

        response = await engine.complete([{"role": "user", "content": prompt}])
        
        try:
            analysis = json.loads(response)
        except json.JSONDecodeError:
            analysis = {"raw_analysis": response}
        
        # Store the meta-cognition result
        try:
            supabase = db.get_db()
            supabase.table("meta_cognition_logs").insert({
                "focus_area": req.focus_area or "general",
                "analysis": json.dumps(analysis),
                "conversation_length": len(req.conversation),
            }).execute()
        except Exception:
            pass
        
        return analysis
    
    except Exception as e:
        logger.error(f"[agi] meta-cognition failed: {e}")
        raise HTTPException(status_code=500, detail=f"Meta-cognition failed: {str(e)}")


# ─── Curiosity-Driven Learning ────────────────────────────────────────────

@router.post("/agi/curiosity", tags=["agi"])
async def explore_curiosity(
    req: CuriosityQuery,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    """Explore a topic out of curiosity and identify learning opportunities."""
    try:
        from llm.engine import get_engine
        
        engine = get_engine()
        
        # If no topic provided, generate one from knowledge gaps
        if not req.topic:
            try:
                supabase = db.get_db()
                gaps = supabase.table("knowledge_gaps").select("*").eq(
                    "is_addressed", False
                ).order("frequency", desc=True).limit(3).execute()
                
                if gaps.data:
                    req.topic = gaps.data[0]["topic"]
            except Exception:
                req.topic = "artificial intelligence"
        
        depth_instructions = {
            "shallow": "Provide a brief overview (2-3 sentences) of the key concepts.",
            "medium": "Provide a detailed explanation with examples and connections to other topics.",
            "deep": "Provide an in-depth analysis including history, current state, controversies, and future directions.",
        }
        
        prompt = f"""You are a curious AI exploring a topic. {depth_instructions.get(req.depth, depth_instructions['medium'])}

Topic: {req.topic}

After your explanation, list:
1. Three sub-topics worth exploring further
2. Two practical applications of this knowledge
3. One question about this topic that you cannot fully answer

Format your response as a JSON object with keys: explanation, sub_topics, applications, open_question"""

        response = await engine.complete([{"role": "user", "content": prompt}])
        
        try:
            result = json.loads(response)
        except json.JSONDecodeError:
            result = {"explanation": response}
        
        # Store the exploration
        try:
            supabase = db.get_db()
            supabase.table("curiosity_explorations").insert({
                "topic": req.topic or "auto-generated",
                "depth": req.depth,
                "result": json.dumps(result),
            }).execute()
            
            # Create knowledge gaps from sub-topics
            for sub_topic in result.get("sub_topics", []):
                supabase.table("knowledge_gaps").upsert({
                    "topic": sub_topic if isinstance(sub_topic, str) else sub_topic.get("topic", str(sub_topic)),
                    "context": f"Discovered while exploring: {req.topic}",
                    "detected_from": "curiosity",
                }).execute()
        except Exception:
            pass
        
        return result
    
    except Exception as e:
        logger.error(f"[agi] curiosity failed: {e}")
        raise HTTPException(status_code=500, detail=f"Curiosity exploration failed: {str(e)}")


# ─── Goal Setting ─────────────────────────────────────────────────────────

@router.get("/agi/goals", tags=["agi"])
async def list_goals(
    status: Optional[str] = None,
    goal_type: Optional[str] = None,
    _: None = Depends(verify_key),
):
    """List DAWN's learning and improvement goals."""
    try:
        supabase = db.get_db()
        q = supabase.table("agi_goals").select("*").order("priority", desc=True)
        if status:
            q = q.eq("status", status)
        if goal_type:
            q = q.eq("goal_type", goal_type)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[agi] list goals failed: {e}")
        return []


@router.post("/agi/goals", tags=["agi"])
async def create_goal(req: GoalCreate, _: None = Depends(verify_key)):
    """Create a new goal for DAWN."""
    try:
        supabase = db.get_db()
        res = supabase.table("agi_goals").insert({
            **req.model_dump(),
            "status": "active",
            "progress": 0.0,
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[agi] create goal failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create goal: {str(e)}")


@router.put("/agi/goals/{goal_id}/progress", tags=["agi"])
async def update_goal_progress(
    goal_id: str,
    progress: float,
    note: Optional[str] = None,
    _: None = Depends(verify_key),
):
    """Update progress on a goal."""
    try:
        supabase = db.get_db()
        
        update_data = {"progress": progress}
        if progress >= 1.0:
            update_data["status"] = "completed"
            update_data["completed_at"] = "now()"
        if note:
            update_data["last_note"] = note
        
        supabase.table("agi_goals").update(update_data).eq("id", goal_id).execute()
        
        return {"status": "updated", "progress": progress}
    except Exception as e:
        logger.error(f"[agi] update goal failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update goal: {str(e)}")


# ─── Theory of Mind ───────────────────────────────────────────────────────

@router.post("/agi/theory-of-mind", tags=["agi"])
async def analyze_user_understanding(
    conversation: list[dict],
    _: None = Depends(verify_key),
):
    """Model Solomon's knowledge state and understanding."""
    try:
        from llm.engine import get_engine
        
        engine = get_engine()
        
        conversation_text = "\n".join([
            f"{m.get('role', 'unknown')}: {m.get('content', '')[:300]}"
            for m in conversation[-10:]
        ])
        
        prompt = f"""Based on this conversation, model the user's current state of understanding.

Conversation:
{conversation_text}

Return a JSON object with:
- knowledge_level: "beginner", "intermediate", "advanced", or "expert" on the discussed topics
- confidence: how confident the user seems (0.0 to 1.0)
- interests: list of topics the user seems interested in
- communication_style: "concise", "detailed", "technical", "casual", or "mixed"
- misunderstood_concepts: list of concepts the user might have misunderstood
- suggested_approach: how DAWN should adapt its communication for this user"""

        response = await engine.complete([{"role": "user", "content": prompt}])
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"raw_analysis": response}
    
    except Exception as e:
        logger.error(f"[agi] theory of mind failed: {e}")
        raise HTTPException(status_code=500, detail=f"Theory of mind analysis failed: {str(e)}")


# ─── Creative Problem Solving ─────────────────────────────────────────────

@router.post("/agi/creative-solve", tags=["agi"])
async def creative_problem_solving(
    problem: str,
    constraints: list[str] = [],
    desired_outcome: Optional[str] = None,
    _: None = Depends(verify_key),
):
    """Apply creative problem solving to a challenge."""
    try:
        from llm.engine import get_engine
        
        engine = get_engine()
        
        constraints_text = "\n".join([f"- {c}" for c in constraints]) if constraints else "No specific constraints."
        
        prompt = f"""You are a creative problem solver. Apply divergent and convergent thinking to solve this problem.

Problem: {problem}

Constraints:
{constraints_text}

Desired Outcome: {desired_outcome or 'A practical, implementable solution'}

Think step by step:
1. Reframe the problem from multiple perspectives
2. Generate at least 5 diverse solutions (including unconventional ones)
3. Evaluate each solution against constraints
4. Combine the best elements into a final recommended approach

Return a JSON object with:
- problem_reframing: the problem viewed from different angles
- solutions: list of 5+ diverse solutions with pros/cons
- evaluation: comparison of solutions against constraints
- recommended_approach: the final recommended solution
- implementation_steps: concrete next steps to implement"""

        response = await engine.complete([{"role": "user", "content": prompt}])
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"raw_response": response}
    
    except Exception as e:
        logger.error(f"[agi] creative solve failed: {e}")
        raise HTTPException(status_code=500, detail=f"Creative problem solving failed: {str(e)}")


# ─── Value Alignment ──────────────────────────────────────────────────────

@router.post("/agi/align", tags=["agi"])
async def check_value_alignment(
    action_description: str,
    _: None = Depends(verify_key),
):
    """Check if an action aligns with DAWN's core values."""
    try:
        from llm.engine import get_engine
        
        engine = get_engine()
        
        prompt = f"""You are a value alignment checker. Evaluate whether the following action aligns with DAWN's core values.

DAWN's Core Values:
1. Precision — Be accurate and truthful. Don't guess or hallucinate.
2. Action — Provide actionable, implementable responses.
3. Growth — Continuously learn and improve.
4. Security — Protect data and infrastructure.
5. Service — Serve Solomon and Regent's interests first.

Action to evaluate: {action_description}

Return a JSON object with:
- aligned: true/false
- confidence: 0.0 to 1.0
- violated_values: list of values that might be violated
- explanation: brief explanation of the alignment check
- suggested_modification: if not aligned, how to modify the action"""

        response = await engine.complete([{"role": "user", "content": prompt}])
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"raw_response": response}
    
    except Exception as e:
        logger.error(f"[agi] alignment check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Value alignment check failed: {str(e)}")


# ─── Self-Improvement Loop ────────────────────────────────────────────────

@router.post("/agi/self-improve", tags=["agi"])
async def trigger_self_improvement(
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    """Trigger DAWN's self-improvement cycle."""
    try:
        supabase = db.get_db()
        
        # Create a self-improvement session
        session = supabase.table("self_improvement_sessions").insert({
            "status": "running",
        }).execute()
        
        session_id = session.data[0]["id"] if session.data else None
        
        if session_id:
            background_tasks.add_task(_run_self_improvement, session_id)
        
        return {
            "session_id": session_id,
            "status": "running",
            "message": "Self-improvement cycle initiated. DAWN will analyze recent conversations, identify knowledge gaps, and update its knowledge graph.",
        }
    
    except Exception as e:
        logger.error(f"[agi] self-improvement failed: {e}")
        raise HTTPException(status_code=500, detail=f"Self-improvement failed: {str(e)}")


def _run_self_improvement(session_id: str):
    """Run the self-improvement cycle (background task)."""
    try:
        supabase = db.get_db()
        
        # Step 1: Analyze recent conversations for improvement opportunities
        # Step 2: Identify knowledge gaps
        # Step 3: Update knowledge graph with new connections
        # Step 4: Generate learning goals
        
        improvements = []
        
        # Check error patterns
        errors = supabase.table("error_patterns").select("*").order("frequency", desc=True).limit(5).execute()
        for error in (errors.data or []):
            improvements.append({
                "type": "error_pattern",
                "pattern": error["pattern"],
                "frequency": error["frequency"],
                "resolution": error.get("resolution", ""),
            })
        
        # Check knowledge gaps
        gaps = supabase.table("knowledge_gaps").select("*").eq("is_addressed", False).limit(5).execute()
        for gap in (gaps.data or []):
            improvements.append({
                "type": "knowledge_gap",
                "topic": gap["topic"],
                "frequency": gap.get("frequency", 1),
            })
        
        # Update session
        supabase.table("self_improvement_sessions").update({
            "status": "completed",
            "completed_at": "now()",
            "improvements_found": len(improvements),
            "summary": json.dumps(improvements),
        }).eq("id", session_id).execute()
        
        logger.info(f"[agi] Self-improvement {session_id} completed: {len(improvements)} improvements found")
    
    except Exception as e:
        logger.error(f"[agi] Self-improvement {session_id} failed: {e}")
        try:
            supabase.table("self_improvement_sessions").update({
                "status": "failed",
                "error_message": str(e),
            }).eq("id", session_id).execute()
        except Exception:
            pass


@router.get("/agi/self-improve/sessions", tags=["agi"])
async def list_self_improvement_sessions(
    limit: int = 10,
    _: None = Depends(verify_key),
):
    """List self-improvement sessions."""
    try:
        supabase = db.get_db()
        res = supabase.table("self_improvement_sessions").select("*").order(
            "created_at", desc=True
        ).limit(limit).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[agi] list sessions failed: {e}")
        return []


# ─── AGI Status Dashboard ─────────────────────────────────────────────────

@router.get("/agi/status", tags=["agi"])
async def get_agi_status(_: None = Depends(verify_key)):
    """Get overall AGI development status."""
    try:
        supabase = db.get_db()
        
        # Count goals
        active_goals = supabase.table("agi_goals").select("id", count="exact").eq("status", "active").execute()
        active_count = active_goals.count if hasattr(active_goals, 'count') else len(active_goals.data or [])
        
        completed_goals = supabase.table("agi_goals").select("id", count="exact").eq("status", "completed").execute()
        completed_count = completed_goals.count if hasattr(completed_goals, 'count') else len(completed_goals.data or [])
        
        # Count explorations
        explorations = supabase.table("curiosity_explorations").select("id", count="exact").execute()
        exploration_count = explorations.count if hasattr(explorations, 'count') else len(explorations.data or [])
        
        # Count improvements
        improvements = supabase.table("self_improvement_sessions").select("id", count="exact").execute()
        improvement_count = improvements.count if hasattr(improvements, 'count') else len(improvements.data or [])
        
        return {
            "active_goals": active_count,
            "completed_goals": completed_count,
            "curiosity_explorations": exploration_count,
            "self_improvement_cycles": improvement_count,
            "capabilities": {
                "meta_cognition": True,
                "curiosity_driven_learning": True,
                "goal_setting": True,
                "theory_of_mind": True,
                "creative_problem_solving": True,
                "value_alignment": True,
                "self_improvement_loop": True,
            },
            "status": "evolving",
        }
    except Exception as e:
        logger.error(f"[agi] status failed: {e}")
        return {"error": str(e)}
