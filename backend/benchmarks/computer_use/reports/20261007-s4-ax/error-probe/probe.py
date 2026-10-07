import asyncio, hashlib, json, os
from pathlib import Path
from dotenv import dotenv_values
from typesafe_sdk import AsyncTypeSafeClient, TypeSafeAPIError
from tank_backend.llm import decision_model as module
from tank_backend.llm.decision_profile import DecisionModelProfile
from tank_backend.llm.task_decision_model import TaskDecisionModel
from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
from tank_backend.benchmarks.spend_http import ContextWindowContract
from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

async def main():
    output = Path('/tmp/tank-jev-error-probe-20261007')
    output.mkdir(exist_ok=False)
    request = json.loads(Path('/tmp/tank-s4-ax-diagnostic-20261007/result.json').read_text())['rows'][0]['calls'][0]['request']
    recipe = {'request_sha256': hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'request_limit':1,'nano_usd_limit':3000000,'endpoint':'https://api.typesafe.ai/v1/systemone',
              'desktop_actions':0,'purpose':'Capture sanitized API error for the previously rejected synthetic AX request'}
    (output/'freeze.json').write_text(json.dumps(recipe,indent=2)+'\n')
    credential = os.environ.get('TYPESAFE_API_KEY') or dotenv_values(Path('core/.env')).get('TYPESAFE_API_KEY') or ''
    captured = {}
    class DiagnosticClient(AsyncTypeSafeClient):
        async def system_one(self,*args,**kwargs):
            try:
                return await super().system_one(*args,**kwargs)
            except TypeSafeAPIError as exc:
                body = json.dumps(exc.body,ensure_ascii=False).replace(credential,'[REDACTED]')
                captured.update(error_type=type(exc).__name__,http_status=exc.status,body=body[:2000])
                raise
    module.AsyncTypeSafeClient = DiagnosticClient
    ledger = SpendLedger(SpendLimit(131072,3000000),request_limit=1,journal=output/'spend.jsonl')
    ledger.start_trial('diagnosis',SpendLimit(131072,3000000))
    policy = BenchmarkModelPolicy(ledger,(ContextWindowContract(recipe['endpoint'],'jev-1.13.0',
        TokenAllowance(65536,65536,42,0),'one-request diagnostic',output_cap_required=False),))
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({'network'})),SubAgentBudget(),asyncio.Event(),model_policy=policy)
    model = module.DecisionModel(DecisionModelProfile(recipe['endpoint'],'jev-1.13.0','KEY'),credential=credential)
    task = TaskDecisionModel('diagnosis',ctx,model)
    question = request['questions']['next_action']
    try:
        result=await task.choose(state=request['state'],instructions=question['instructions'],options=question['criteria'])
        captured['returned_choice']=result.choice
    except Exception as exc:
        captured['terminal_error_type']=type(exc).__name__
    finally:
        await task.aclose()
        await model.aclose()
        captured['spend']=ledger.snapshot()
        ledger.close()
        (output/'result.json').write_text(json.dumps(captured,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in captured.items() if k!='spend'},ensure_ascii=False))
asyncio.run(main())
