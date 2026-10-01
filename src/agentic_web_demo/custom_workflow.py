"""Independent LangGraph/CrewAI orchestration; adapters and guards are shared."""


def run_steps(framework, actions, progress):
    trace, output, errors = [], {}, []

    def step(index):
        if index >= len(actions) or errors:
            return
        name, action = actions[index]
        progress(name)
        try:
            output.update(action() or {})
            stage_status = (
                "failed"
                if output.get("failed_stage") == name or output.get("status") == "failed"
                else output.get("status")
                if output.get("status") in {"needs_input", "unsupported"}
                else "ok"
            )
            trace.append(f"{name}:{stage_status}")
        except Exception as exc:
            trace.append(name + ":failed")
            # Do not let orchestration logging serialize provider exceptions or page content.
            errors.append(exc)

    if framework == "langgraph":
        from langgraph.graph import END, START, StateGraph
        from langsmith import tracing_context

        graph = StateGraph(dict)
        previous = START
        for index, (name, _) in enumerate(actions):

            def node(state, i=index):
                step(i)
                return {"stage": actions[i][0]}

            graph.add_node(name, node)
            graph.add_edge(previous, name)
            previous = name
        graph.add_edge(previous, END)
        with tracing_context(enabled=False):
            graph.compile().invoke({})
    elif framework == "crewai":
        from agentic_web_demo.agents.crewai_runtime import configure

        configure()
        from crewai.flow.flow import Flow, listen, start

        class WebsiteFlow(Flow[dict]):
            @start()
            def first(self):
                step(0)

            @listen(first)
            def second(self):
                step(1)

            @listen(second)
            def third(self):
                step(2)

            @listen(third)
            def fourth(self):
                step(3)

        WebsiteFlow(tracing=False, suppress_flow_events=True).kickoff()
    else:
        raise ValueError("Unknown framework")
    if errors:
        errors[0].workflow_trace = trace
        raise errors[0]
    return {**output, "trace": trace}
