"""
v17.0 — Natural Language Data Analysis
SQL generation, data profiling, statistical analysis, time series, text analytics
"""
import json
import logging
import pandas as pd
import io
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Any
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ─── Schemas ──────────────────────────────────────────────────────────────

class NLQueryRequest(BaseModel):
    question: str
    table_schema: str  # CREATE TABLE statement or schema description
    dialect: str = "postgresql"

class SQLResult(BaseModel):
    sql: str
    results: list[dict] = []
    error: Optional[str] = None
    execution_time_ms: float = 0.0

class DataProfileRequest(BaseModel):
    data: list[dict]
    columns: Optional[list[str]] = None

class StatisticalTestRequest(BaseModel):
    test_type: str  # 't_test', 'chi_square', 'correlation', 'regression', 'anova'
    data: list[dict]
    x_column: str
    y_column: Optional[str] = None
    groups_column: Optional[str] = None

class TimeSeriesRequest(BaseModel):
    data: list[dict]
    date_column: str
    value_column: str
    analysis_type: str = "trend"  # 'trend', 'seasonality', 'forecast', 'anomaly'
    forecast_periods: int = 30

# ─── NL → SQL ─────────────────────────────────────────────────────────────

@router.post("/data-analysis/nl-to-sql", tags=["data-analysis"])
async def natural_language_to_sql(
    req: NLQueryRequest,
    _: None = Depends(verify_key),
):
    """Convert natural language to SQL query."""
    try:
        from llm.engine import get_engine
        
        engine = get_engine()
        
        prompt = f"""You are a SQL expert. Convert the following natural language question into a {req.dialect} SQL query.

Database Schema:
{req.table_schema}

Question: {req.question}

Return ONLY the SQL query, no explanation, no markdown formatting."""

        messages = [{"role": "user", "content": prompt}]
        sql = await engine.complete(messages)
        
        # Clean up the SQL
        sql = sql.strip()
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        sql = sql.strip()
        
        return {"sql": sql, "question": req.question, "dialect": req.dialect}
    except Exception as e:
        logger.error(f"[data-analysis] NL→SQL failed: {e}")
        raise HTTPException(status_code=500, detail=f"NL→SQL failed: {str(e)}")


@router.post("/data-analysis/execute-sql", tags=["data-analysis"])
async def execute_sql_query(
    req: "SQLQueryRequest",
    _: None = Depends(verify_key),
):
    """Execute a SQL query against the connected database and return results."""
    import time
    start = time.time()
    
    try:
        supabase = db.get_db()
        
        # Execute raw SQL via Supabase's rpc or direct query
        # Note: This uses the service_role key which has full access
        res = supabase.rpc("exec_sql", {"query_text": req.sql}).execute()
        
        elapsed = (time.time() - start) * 1000
        
        return SQLResult(
            sql=req.sql,
            results=res.data if res.data else [],
            execution_time_ms=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.error(f"[data-analysis] SQL execution failed: {e}")
        return SQLResult(
            sql=req.sql,
            error=str(e),
            execution_time_ms=round(elapsed, 2),
        )


class SQLQueryRequest(BaseModel):
    sql: str
    limit: int = 100


# ─── Data Profiling ───────────────────────────────────────────────────────

@router.post("/data-analysis/profile", tags=["data-analysis"])
async def profile_data(
    req: DataProfileRequest,
    _: None = Depends(verify_key),
):
    """Profile a dataset: statistics, missing values, data types, distributions."""
    try:
        df = pd.DataFrame(req.data)
        
        if req.columns:
            df = df[req.columns]
        
        profile = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": {},
            "memory_usage_mb": df.memory_usage(deep=True).sum() / 1024 / 1024,
        }
        
        for col in df.columns:
            col_data = df[col]
            col_profile = {
                "dtype": str(col_data.dtype),
                "non_null_count": int(col_data.count()),
                "null_count": int(col_data.isna().sum()),
                "null_percentage": round(float(col_data.isna().mean() * 100), 2),
                "unique_count": int(col_data.nunique()),
            }
            
            # Numeric columns
            if pd.api.types.is_numeric_dtype(col_data):
                col_profile.update({
                    "min": float(col_data.min()) if not col_data.isna().all() else None,
                    "max": float(col_data.max()) if not col_data.isna().all() else None,
                    "mean": float(col_data.mean()) if not col_data.isna().all() else None,
                    "median": float(col_data.median()) if not col_data.isna().all() else None,
                    "std": float(col_data.std()) if not col_data.isna().all() else None,
                    "q1": float(col_data.quantile(0.25)) if not col_data.isna().all() else None,
                    "q3": float(col_data.quantile(0.75)) if not col_data.isna().all() else None,
                    "skewness": float(col_data.skew()) if not col_data.isna().all() else None,
                    "kurtosis": float(col_data.kurtosis()) if not col_data.isna().all() else None,
                })
            
            # String/categorical columns
            elif pd.api.types.is_object_dtype(col_data) or pd.api.types.is_categorical_dtype(col_data):
                value_counts = col_data.value_counts().head(10).to_dict()
                col_profile.update({
                    "top_values": {str(k): int(v) for k, v in value_counts.items()},
                    "min_length": int(col_data.astype(str).str.len().min()) if not col_data.isna().all() else 0,
                    "max_length": int(col_data.astype(str).str.len().max()) if not col_data.isna().all() else 0,
                })
            
            # Datetime columns
            elif pd.api.types.is_datetime64_dtype(col_data):
                col_profile.update({
                    "min_date": str(col_data.min()) if not col_data.isna().all() else None,
                    "max_date": str(col_data.max()) if not col_data.isna().all() else None,
                    "range_days": int((col_data.max() - col_data.min()).days) if not col_data.isna().all() else 0,
                })
            
            profile["columns"][col] = col_profile
        
        return profile
    except Exception as e:
        logger.error(f"[data-analysis] Profiling failed: {e}")
        raise HTTPException(status_code=500, detail=f"Profiling failed: {str(e)}")


# ─── Statistical Analysis ─────────────────────────────────────────────────

@router.post("/data-analysis/statistical-test", tags=["data-analysis"])
async def statistical_test(
    req: StatisticalTestRequest,
    _: None = Depends(verify_key),
):
    """Run statistical tests on data."""
    try:
        from scipy import stats as scipy_stats
        
        df = pd.DataFrame(req.data)
        
        if req.test_type == "correlation":
            x = df[req.x_column].dropna()
            y = df[req.y_column].dropna() if req.y_column else df[req.x_column].dropna()
            
            # Ensure same length
            min_len = min(len(x), len(y))
            x, y = x[:min_len], y[:min_len]
            
            pearson_r, pearson_p = scipy_stats.pearsonr(x, y)
            spearman_r, spearman_p = scipy_stats.spearmanr(x, y)
            
            return {
                "test_type": "correlation",
                "x_column": req.x_column,
                "y_column": req.y_column,
                "pearson": {"r": round(pearson_r, 4), "p_value": round(pearson_p, 4)},
                "spearman": {"rho": round(spearman_r, 4), "p_value": round(spearman_p, 4)},
                "sample_size": min_len,
                "interpretation": _interpret_correlation(pearson_r, pearson_p),
            }
        
        elif req.test_type == "t_test":
            if req.groups_column:
                groups = df.groupby(req.groups_column)[req.x_column].apply(list)
                if len(groups) == 2:
                    t_stat, p_val = scipy_stats.ttest_ind(groups.iloc[0], groups.iloc[1])
                    return {
                        "test_type": "independent_t_test",
                        "group_column": req.groups_column,
                        "groups": list(groups.index),
                        "t_statistic": round(t_stat, 4),
                        "p_value": round(p_val, 4),
                        "significant": p_val < 0.05,
                        "interpretation": _interpret_ttest(t_stat, p_val),
                    }
            
            # One-sample t-test
            data = df[req.x_column].dropna()
            t_stat, p_val = scipy_stats.ttest_1samp(data, 0)
            return {
                "test_type": "one_sample_t_test",
                "column": req.x_column,
                "t_statistic": round(t_stat, 4),
                "p_value": round(p_val, 4),
                "mean": float(data.mean()),
                "significant": p_val < 0.05,
            }
        
        elif req.test_type == "anova":
            if req.groups_column:
                groups = [group[req.x_column].dropna().values for _, group in df.groupby(req.groups_column)]
                f_stat, p_val = scipy_stats.f_oneway(*groups)
                return {
                    "test_type": "one_way_anova",
                    "group_column": req.groups_column,
                    "value_column": req.x_column,
                    "f_statistic": round(f_stat, 4),
                    "p_value": round(p_val, 4),
                    "significant": p_val < 0.05,
                    "group_count": len(groups),
                }
        
        elif req.test_type == "chi_square":
            contingency = pd.crosstab(df[req.x_column], df[req.y_column])
            chi2, p_val, dof, expected = scipy_stats.chi2_contingency(contingency)
            return {
                "test_type": "chi_square",
                "x_column": req.x_column,
                "y_column": req.y_column,
                "chi2": round(chi2, 4),
                "p_value": round(p_val, 4),
                "degrees_of_freedom": int(dof),
                "significant": p_val < 0.05,
            }
        
        elif req.test_type == "regression":
            from sklearn.linear_model import LinearRegression
            
            X = df[[req.x_column]].dropna()
            y = df[req.y_column].dropna() if req.y_column else df[req.x_column].dropna()
            
            # Align
            common_idx = X.index.intersection(y.index)
            X = X.loc[common_idx]
            y = y.loc[common_idx]
            
            model = LinearRegression()
            model.fit(X, y)
            
            r_squared = model.score(X, y)
            
            return {
                "test_type": "linear_regression",
                "x_column": req.x_column,
                "y_column": req.y_column or req.x_column,
                "coefficient": round(float(model.coef_[0]), 4),
                "intercept": round(float(model.intercept_), 4),
                "r_squared": round(r_squared, 4),
                "sample_size": len(common_idx),
                "equation": f"{req.y_column or 'y'} = {round(float(model.coef_[0]), 4)} * {req.x_column} + {round(float(model.intercept_), 4)}",
            }
        
        raise HTTPException(status_code=400, detail=f"Unknown test type: {req.test_type}")
    
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"Required library not installed: {str(e)}")
    except Exception as e:
        logger.error(f"[data-analysis] Statistical test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Statistical test failed: {str(e)}")


def _interpret_correlation(r: float, p: float) -> str:
    if p > 0.05:
        return "No statistically significant correlation (p > 0.05)"
    strength = "very strong" if abs(r) > 0.8 else "strong" if abs(r) > 0.6 else "moderate" if abs(r) > 0.4 else "weak"
    direction = "positive" if r > 0 else "negative"
    return f"Statistically significant {strength} {direction} correlation (r={r:.3f}, p={p:.4f})"


def _interpret_ttest(t: float, p: float) -> str:
    if p > 0.05:
        return "No statistically significant difference (p > 0.05)"
    return f"Statistically significant difference (t={t:.3f}, p={p:.4f})"


# ─── Time Series Analysis ─────────────────────────────────────────────────

@router.post("/data-analysis/time-series", tags=["data-analysis"])
async def analyze_time_series(
    req: TimeSeriesRequest,
    _: None = Depends(verify_key),
):
    """Analyze time series data: trend, seasonality, anomalies."""
    try:
        df = pd.DataFrame(req.data)
        df[req.date_column] = pd.to_datetime(df[req.date_column])
        df = df.sort_values(req.date_column)
        
        result = {
            "date_column": req.date_column,
            "value_column": req.value_column,
            "analysis_type": req.analysis_type,
            "data_points": len(df),
            "date_range": {
                "start": str(df[req.date_column].min()),
                "end": str(df[req.date_column].max()),
            },
        }
        
        values = df[req.value_column]
        
        # Basic statistics
        result["statistics"] = {
            "min": float(values.min()),
            "max": float(values.max()),
            "mean": float(values.mean()),
            "median": float(values.median()),
            "std": float(values.std()),
        }
        
        if req.analysis_type in ("trend", "forecast"):
            from sklearn.linear_model import LinearRegression
            import numpy as np
            
            # Trend analysis
            X = np.arange(len(df)).reshape(-1, 1)
            y = values.values
            
            model = LinearRegression()
            model.fit(X, y)
            
            trend_direction = "upward" if model.coef_[0] > 0 else "downward"
            result["trend"] = {
                "direction": trend_direction,
                "slope": round(float(model.coef_[0]), 4),
                "r_squared": round(float(model.score(X, y)), 4),
                "change_per_period": round(float(model.coef_[0]), 4),
            }
            
            # Forecast
            if req.analysis_type == "forecast" and req.forecast_periods > 0:
                future_X = np.arange(len(df), len(df) + req.forecast_periods).reshape(-1, 1)
                predictions = model.predict(future_X)
                
                result["forecast"] = {
                    "periods": req.forecast_periods,
                    "predictions": [round(float(p), 4) for p in predictions],
                    "last_known_value": float(values.iloc[-1]),
                    "forecast_final_value": round(float(predictions[-1]), 4),
                }
        
        if req.analysis_type == "seasonality":
            # Simple seasonality detection using autocorrelation
            import numpy as np
            
            values_series = values.values
            if len(values_series) > 10:
                autocorr = np.correlate(values_series - values_series.mean(), 
                                        values_series - values_series.mean(), mode='full')
                autocorr = autocorr[len(autocorr)//2:]
                autocorr = autocorr / autocorr[0]
                
                # Find peaks in autocorrelation
                peaks = []
                for i in range(2, len(autocorr) - 2):
                    if autocorr[i] > autocorr[i-1] and autocorr[i] > autocorr[i+1] and autocorr[i] > 0.3:
                        peaks.append({"lag": i, "correlation": round(float(autocorr[i]), 4)})
                
                result["seasonality"] = {
                    "detected": len(peaks) > 0,
                    "peaks": peaks[:5],
                    "suggested_period": peaks[0]["lag"] if peaks else None,
                }
        
        if req.analysis_type == "anomaly":
            # Simple anomaly detection using IQR
            import numpy as np
            
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            
            anomalies = df[(values < lower_bound) | (values > upper_bound)]
            
            result["anomalies"] = {
                "count": len(anomalies),
                "threshold_lower": float(lower_bound),
                "threshold_upper": float(upper_bound),
                "anomaly_points": [
                    {
                        "date": str(row[req.date_column]),
                        "value": float(row[req.value_column]),
                        "deviation": "low" if float(row[req.value_column]) < lower_bound else "high",
                    }
                    for _, row in anomalies.iterrows()
                ][:50],  # Limit to 50
            }
        
        return result
    
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"Required library not installed: {str(e)}")
    except Exception as e:
        logger.error(f"[data-analysis] Time series analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Time series analysis failed: {str(e)}")


# ─── Text Analytics ───────────────────────────────────────────────────────

@router.post("/data-analysis/text-analytics", tags=["data-analysis"])
async def analyze_text(
    text: str = Form(...),
    analysis_types: str = Form("sentiment,entities,keywords,summary"),
    _: None = Depends(verify_key),
):
    """Analyze text: sentiment, entities, keywords, summarization."""
    try:
        from llm.engine import get_engine
        
        engine = get_engine()
        types = [t.strip() for t in analysis_types.split(",")]
        result = {"text_length": len(text), "word_count": len(text.split())}
        
        if "sentiment" in types:
            prompt = f"""Analyze the sentiment of this text. Return ONLY a JSON object with:
- sentiment: "positive", "negative", or "neutral"
- score: a number from -1.0 to 1.0
- confidence: 0.0 to 1.0
- key_emotions: list of emotions detected

Text: {text[:2000]}"""
            
            resp = await engine.complete([{"role": "user", "content": prompt}])
            try:
                result["sentiment"] = json.loads(resp)
            except json.JSONDecodeError:
                result["sentiment"] = {"raw": resp}
        
        if "entities" in types:
            prompt = f"""Extract named entities from this text. Return ONLY a JSON object with:
- people: list of person names
- organizations: list of organization names
- locations: list of location names
- dates: list of dates mentioned
- other: list of other notable entities

Text: {text[:2000]}"""
            
            resp = await engine.complete([{"role": "user", "content": prompt}])
            try:
                result["entities"] = json.loads(resp)
            except json.JSONDecodeError:
                result["entities"] = {"raw": resp}
        
        if "keywords" in types:
            prompt = f"""Extract the top 10 keywords from this text. Return ONLY a JSON array of objects with:
- word: the keyword
- relevance: 0.0 to 1.0

Text: {text[:2000]}"""
            
            resp = await engine.complete([{"role": "user", "content": prompt}])
            try:
                result["keywords"] = json.loads(resp)
            except json.JSONDecodeError:
                result["keywords"] = {"raw": resp}
        
        if "summary" in types:
            prompt = f"""Summarize this text in 2-3 sentences. Be concise and capture the key points.

Text: {text[:3000]}"""
            
            result["summary"] = await engine.complete([{"role": "user", "content": prompt}])
        
        return result
    
    except Exception as e:
        logger.error(f"[data-analysis] Text analytics failed: {e}")
        raise HTTPException(status_code=500, detail=f"Text analytics failed: {str(e)}")


# ─── Data Upload & Preview ────────────────────────────────────────────────

@router.post("/data-analysis/upload", tags=["data-analysis"])
async def upload_dataset(
    file: UploadFile = File(...),
    _: None = Depends(verify_key),
):
    """Upload a CSV/Excel file for analysis and return a preview."""
    try:
        contents = await file.read()
        
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif file.filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use CSV or Excel.")
        
        return {
            "filename": file.filename,
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "preview": json.loads(df.head(10).to_json(orient="records")),
            "memory_estimate_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        }
    except Exception as e:
        logger.error(f"[data-analysis] Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
