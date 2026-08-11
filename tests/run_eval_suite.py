import os
import json
import sys
import asyncio
from dotenv import load_dotenv

# Ensure we can import from src/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

def resolve_api_key():
    """Resolves Gemini API Key, attempting Secret Manager fallback if not in env."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key
        
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    secret_name = os.environ.get("GEMINI_API_KEY_SECRET_NAME", "gemini-api-key")
    
    if project_id:
        try:
            from google.adk.integrations.secret_manager.secret_client import SecretManagerClient
            print(f"Attempting to fetch API key from Google Secret Manager (project={project_id}, secret={secret_name})...")
            client = SecretManagerClient()
            resource_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
            secret_val = client.get_secret(resource_path)
            if secret_val:
                os.environ["GEMINI_API_KEY"] = secret_val
                return secret_val
        except Exception as e:
            print(f"Warning: Could not fetch secret from Secret Manager: {e}")
            
    return None

# Load environment variables from .env file before imports that instantiate clients
load_dotenv()
resolve_api_key()

from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

from code_review_agent.agent import app


async def run_evaluation_async():
    dataset_path = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
    if not os.path.exists(dataset_path):
        print(f"Error: Golden dataset not found at {dataset_path}")
        sys.exit(1)
        
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    print(f"Loaded {len(cases)} evaluation test cases.")
    all_passed = True
    
    # Configure persistent SQLite database (Category 2: Persistent Session State)
    db_path = os.path.join(os.path.dirname(__file__), "eval_sessions.db")
    session_service = SqliteSessionService(db_path=db_path)
    
    for case in cases:
        case_id = case["id"]
        filepath = case["filepath"]
        code = case["code"]
        expected_issues = case["expected_issues"]
        
        print(f"\n--- Running Case: {case_id} ({filepath}) ---")
        
        # 1. Write the test code file to disk so the agent can read it
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
            
        try:
            # 2. Set up the runner with the persistent SQLite session service
            runner = Runner(
                app=app,
                session_service=session_service,
                auto_create_session=True
            )
            
            # 3. Create the review instruction
            prompt = f"Please review the file '{filepath}' and report any issues."
            new_msg = types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)]
            )
            
            # 4. Execute the agent asynchronously (Category 2: Async memory/runner execution)
            print(f"Sending prompt: {prompt}")
            response_text = ""
            async for event in runner.run_async(user_id="eval_user", session_id=f"sess_{case_id}", new_message=new_msg):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
            
            print("Agent Output Response:")
            print("=========================================")
            print(response_text)
            print("=========================================")
            
            # 5. Evaluate the agent's findings
            passed = True
            for issue in expected_issues:
                # Simple keyword matching to assert agent found expected issues
                if issue.lower() not in response_text.lower():
                    print(f"❌ FAIL: Expected agent to flag '{issue}', but it was not mentioned.")
                    passed = False
                else:
                    print(f"✅ PASS: Correctly flagged '{issue}'.")
                    
            if not expected_issues:
                # If expecting clean, verify it doesn't complain of critical bugs
                if "error" in response_text.lower() or "violation" in response_text.lower() or "bug" in response_text.lower():
                    # Check if it actually flagged something that looks like an issue
                    # But it's fine if it's clean
                    if "no issues" in response_text.lower() or "correct" in response_text.lower() or "clean" in response_text.lower():
                         print("✅ PASS: Correctly identified as clean/no major issues.")
                    else:
                         print("⚠️ WARNING: Agent output is ambiguous on clean file, check review report.")
                else:
                     print("✅ PASS: Correctly identified as clean.")
                     
            if passed:
                print(f"🎉 Case '{case_id}' completed successfully.")
            else:
                all_passed = False
                
        except Exception as e:
            print(f"❌ ERROR: Case '{case_id}' failed with exception: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
        finally:
            # Clean up the file
            if os.path.exists(filepath):
                os.remove(filepath)
                
    # Clean up evaluation sqlite database files
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        # SQLite creates extra temporary lock files on write sometimes
        for extra_file in [f"{db_path}-shm", f"{db_path}-wal", f"{db_path}-journal"]:
            if os.path.exists(extra_file):
                os.remove(extra_file)
    except Exception as e:
        print(f"Warning: Could not remove evaluation db files: {e}")

    if all_passed:
        print("\n🏆 EVALUATION SUITE COMPLETED: ALL CASES PASSED!")
        sys.exit(0)
    else:
        print("\n❌ EVALUATION SUITE FAILED: Regression detected.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_evaluation_async())
