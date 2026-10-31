"""Haystack adapter — fake ChatMessage objects and dicts, no haystack."""

from enum import Enum

from attest.adapters.haystack import from_haystack_messages


class ChatRole(str, Enum):  # noqa: UP042 - the shape haystack uses
    USER = "user"
    SYSTEM = "system"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall:
    def __init__(self, tool_name, arguments, id=None):
        self.tool_name = tool_name
        self.arguments = arguments
        self.id = id


class ToolCallResult:
    def __init__(self, result, origin, error=False):
        self.result = result
        self.origin = origin
        self.error = error


class TextContent:
    def __init__(self, text):
        self.text = text


class ChatMessage:
    def __init__(self, role, text=None, tool_calls=None, tool_call_result=None):
        self.role = role
        self.text = text
        self.tool_calls = tool_calls or []
        self.tool_call_result = tool_call_result
        self.tool_call_results = [tool_call_result] if tool_call_result else []


def user(text):
    return ChatMessage(ChatRole.USER, text)


def system(text):
    return ChatMessage(ChatRole.SYSTEM, text)


def assistant(text=None, tool_calls=None):
    return ChatMessage(ChatRole.ASSISTANT, text, tool_calls)


def tool(result, origin, error=False):
    return ChatMessage(ChatRole.TOOL, tool_call_result=ToolCallResult(result, origin, error))


def test_adapts_an_agent_run():
    search = ToolCall("search", {"q": "capital of France"}, "c1")
    messages = [
        system("You answer geography questions."),
        user("What is the capital of France?"),
        assistant("Let me look that up.", [search]),
        tool("Paris is the capital of France.", search),
        assistant("The capital of France is Paris."),
    ]

    traj = from_haystack_messages(messages, allowed_tools=["search"])

    assert traj.task == "What is the capital of France?"
    assert traj.system_prompt == "You answer geography questions."
    assert traj.allowed_tools == ["search"]
    assert len(traj.steps) == 1
    step = traj.steps[0]
    assert step.thought == "Let me look that up."
    assert step.tool_call.name == "search"
    assert step.tool_call.arguments == {"q": "capital of France"}
    assert step.tool_call.output == "Paris is the capital of France."
    assert traj.final_answer == "The capital of France is Paris."


def test_pairs_several_calls_in_one_message_by_origin_id():
    weather = ToolCall("weather", {"city": "Lagos"}, "w")
    time = ToolCall("time", {"city": "Lagos"}, "t")
    messages = [
        user("Weather and time in Lagos?"),
        assistant(tool_calls=[weather, time]),
        tool("14:00", time),
        tool("31C and sunny", weather),
        assistant("It is 31C and 14:00."),
    ]

    calls = [tc for _, tc in from_haystack_messages(messages).tool_calls()]

    assert [(c.name, c.output) for c in calls] == [("weather", "31C and sunny"), ("time", "14:00")]


def test_falls_back_to_order_without_ids():
    first = ToolCall("a", {})
    second = ToolCall("b", {})
    messages = [
        user("go"),
        assistant(tool_calls=[first, second]),
        tool("out a", ToolCall("a", {})),
        tool("out b", ToolCall("b", {})),
        assistant("done"),
    ]
    calls = [tc for _, tc in from_haystack_messages(messages).tool_calls()]
    assert [c.output for c in calls] == ["out a", "out b"]


def test_error_result_keeps_its_text_as_output():
    fetch = ToolCall("fetch", {"url": "x"}, "f")
    messages = [
        user("fetch x"),
        assistant(tool_calls=[fetch]),
        tool("HTTP 404: not found", fetch, error=True),
        assistant("I could not fetch it."),
    ]
    call = from_haystack_messages(messages).steps[0].tool_call
    assert call.output == "HTTP 404: not found"


def test_missing_result_leaves_output_empty():
    messages = [user("go"), assistant(tool_calls=[ToolCall("search", {}, "s")])]
    traj = from_haystack_messages(messages)
    assert traj.steps[0].tool_call.output == ""
    assert traj.final_answer == ""


def test_run_without_tool_calls():
    traj = from_haystack_messages([user("hi"), assistant("hello")])
    assert traj.steps == []
    assert traj.task == "hi"
    assert traj.final_answer == "hello"
    assert traj.system_prompt is None
    assert traj.allowed_tools is None


def test_explicit_task_and_system_prompt_win():
    messages = [system("detected"), user("detected task"), assistant("ok")]
    traj = from_haystack_messages(messages, task="given task", system_prompt="given")
    assert traj.task == "given task"
    assert traj.system_prompt == "given"


def test_joins_text_parts_of_a_content_result():
    lookup = ToolCall("lookup", {}, "l")
    parts = [TextContent("line one"), object(), TextContent("line two")]
    messages = [user("go"), assistant(tool_calls=[lookup]), tool(parts, lookup), assistant("ok")]
    assert from_haystack_messages(messages).steps[0].tool_call.output == "line one\nline two"


def _call_dict(name, arguments, id):
    return {"tool_name": name, "arguments": arguments, "id": id, "extra": None}


def test_accepts_the_to_dict_form():
    search = _call_dict("search", {"q": "a"}, "c1")
    calc = _call_dict("calc", {"x": 1}, "c2")
    messages = [
        {"role": "system", "meta": {}, "name": None, "content": [{"text": "sys"}]},
        {"role": "user", "meta": {}, "name": None, "content": [{"text": "hi"}]},
        {
            "role": "assistant",
            "meta": {},
            "name": None,
            "content": [{"text": "thinking"}, {"tool_call": search}, {"tool_call": calc}],
        },
        {
            "role": "tool",
            "content": [{"tool_call_result": {"result": "boom", "origin": calc, "error": True}}],
        },
        {
            "role": "tool",
            "content": [
                {"tool_call_result": {"result": [{"text": "r1"}], "origin": search, "error": False}}
            ],
        },
        {"role": "assistant", "meta": {}, "name": None, "content": [{"text": "done"}]},
    ]

    traj = from_haystack_messages(messages)

    assert traj.task == "hi"
    assert traj.system_prompt == "sys"
    calls = [tc for _, tc in traj.tool_calls()]
    assert [(c.name, c.arguments, c.output) for c in calls] == [
        ("search", {"q": "a"}, "r1"),
        ("calc", {"x": 1}, "boom"),
    ]
    assert traj.steps[0].thought == "thinking"
    assert traj.final_answer == "done"
