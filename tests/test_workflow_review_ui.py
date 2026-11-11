"""Source-authored local UI cases; not executed during implementation."""

import pytest

from test_dashboard_live_updates import live_ui
from test_extension_handoff_session import worker_page


def test_article_exclusion_reasons_are_collapsed_safe_and_clear_on_next_preview(live_ui):
    result = live_ui.evaluate('''() => {
      const counts = {candidates:2,matched:1,unrelated:1,uncertain:0,invalid:0,
        filtered_out:0,duplicates:0,optional_fields_cleared:0};
      const originalStep = studioStep;
      showReviewCounts({review_counts:counts,topic_assessments:[{
        title:'Captured headline',classification:'not_relevant',
        reason:'<img src=x onerror=alert(1)>',evidence:'A captured source quote',
        record_url:'https://news.example.org/story',source_url:'https://news.example.org/'
      }]});
      const shown = {hidden:topicReview.hidden,open:topicReview.open,
        title:topicReviewTitle.textContent,quote:topicReviewList.querySelector('blockquote').textContent,
        reason:topicReviewList.textContent.includes('<img src=x onerror=alert(1)>'),
        injected:topicReviewList.querySelectorAll('img,script').length,
        href:topicReviewList.querySelector('a').href,unchanged:studioStep===originalStep};
      showReviewCounts({review_counts:{...counts,unrelated:0}});
      return {...shown,cleared:topicReview.hidden && topicReviewList.children.length===0};
    }''')
    assert result == {"hidden": False, "open": False, "title": "Why articles were excluded (1)",
                      "quote": "A captured source quote", "reason": True, "injected": 0,
                      "href": "https://news.example.org/story", "unchanged": True, "cleared": True}


@pytest.mark.parametrize("state", ["awaiting_review", "reviewing", "completed"])
def test_companion_review_uses_persisted_job_after_channel_pruning(worker_page, state):
    result = worker_page.evaluate("""async state => {
      const {config,api}=workerFixture;
      const plan='11111111-1111-4111-8111-111111111111';
      const saved='22222222-2222-4222-8222-222222222222';
      config.state.run={...config.state.run,state,job_id:plan,plan_job_id:plan};
      config.fetchHook=async path => {
        if(path.startsWith('/api/extension/runs/'))
          return {ok:false,status:404,json:async()=>({detail:'Expired channel'})};
        if(path===`/api/custom/jobs/${plan}/workflow`)
          return {ok:true,status:200,json:async()=>({job:{job_id:saved,
            status:'completed',result:{guidance:'Saved'},workflow:{
              plan_job_id:plan,execution_job_id:saved,saved_run_id:'saved-run'}}})};
      };
      const value=await api.handle({operation:'open_review'});
      return {state:value.run.state,job:value.run.job_id,saved:value.run.saved_run_id,
        methods:config.calls.filter(call=>call.path!=='/api/session').map(call=>call.method),
        native:config.events.filter(event=>event.kind==='native_attach').length};
    }""", state)
    assert result == {"state": "completed", "job": "22222222-2222-4222-8222-222222222222",
                      "saved": "saved-run", "methods": ["GET", "GET"], "native": 0}


def test_workflow_relay_permission_is_read_only(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;
      try {await api.relay(config.state,
        '/api/custom/jobs/11111111-1111-4111-8111-111111111111/workflow','POST',{});}
      catch(error){return {error:error.message,calls:config.calls.length};}
    }""")
    assert result == {"error": "unsupported", "calls": 0}


def test_double_approval_click_sends_one_immutable_save_request(live_ui):
    result = live_ui.evaluate("""async()=>{
      webProposal={plan_id:'review-plan',partial:false};webRevision='review-revision';
      webSubmitting=false;
      let finishSave;const requests=[],selected=[];
      window.fixtureApi=(path,data)=>{
        requests.push({path,data});return new Promise(resolve=>{finishSave=resolve;});
      };
      customSelect=async id=>selected.push(id);
      const first=$('web-execute').onclick({currentTarget:$('web-execute')});
      webProposal={plan_id:'other-plan'};webRevision='other-revision';
      await $('web-execute').onclick({currentTarget:$('web-execute')});
      finishSave({job_id:'original-save'});await first;
      return {requests,selected,saving:webSaving};
    }""")
    assert result == {"requests": [{"path": "/api/custom/plans/review-plan/execute",
                                   "data": {"revision": "review-revision", "accept_partial": False}}],
                      "selected": ["original-save"], "saving": False}
