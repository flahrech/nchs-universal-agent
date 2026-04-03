import streamlit as st
import os
import re
from crewai import Agent, Task, Crew, Process
from crewai_tools import TavilySearchTool
from pptx import Presentation
from pptx.util import Pt

# ============================================================
# 1. CONSTANTS & CONFIGURATION
# ============================================================

TOP_20_HOSPITALS = [
    "Cincinnati Children's", "Boston Children's", "CHOP", "Texas Children's",
    "Children's Hospital Los Angeles", "Nationwide Children's", "Children's National",
    "UPMC Children's Pittsburgh", "Seattle Children's", "Johns Hopkins Children's",
    "Stanford Children's", "Colorado Children's", "Children's Healthcare of Atlanta",
    "Riley Children's", "St. Louis Children's", "Phoenix Children's",
    "Nicklaus Children's (NCHS)", "Primary Children's", "Duke Children's",
    "Ann & Robert H. Lurie", "Joe DiMaggio Children's Hospital", "Broward Health"
]

STRATEGIC_FOCUS_AREAS = [
    "Clinical Excellence & Safety", "Operational Efficiency",
    "Financial Sustainability", "Patient/Family Experience",
    "Nursing Retention & Culture", "Digital Health & AI Integration",
    "Quality Management", "Strategy", "Research"
]

DEPTH_OPTIONS = {
    "Executive Brief": {
        "label": "Fast, high-level strategic overview",
        "search_depth": "surface",
        "instruction": (
            "Provide a concise, high-level executive overview. Focus on the 3-5 most impactful findings. "
            "Use bullet points and brief summaries. Prioritize breadth over depth. "
            "Limit each section to 2-3 key points. Total output should be scannable in under 5 minutes."
        )
    },
    "Standard Analysis": {
        "label": "Balanced depth with key data points",
        "search_depth": "standard",
        "instruction": (
            "Provide a well-rounded analysis with supporting data. Include key metrics, specific programs, "
            "and concrete examples for each peer. Balance narrative with numbers. "
            "Each section should be substantive but focused — 3-5 paragraphs or equivalent."
        )
    },
    "Deep Dive": {
        "label": "Comprehensive research with full granularity",
        "search_depth": "deep",
        "instruction": (
            "Conduct exhaustive research. For each peer institution, surface every available data point: "
            "specific program names, dollar amounts, outcome metrics, timelines, staffing ratios, "
            "threshold values, timeliness benchmarks, and implementation details. "
            "Leave no stone unturned. Include nuanced findings, edge cases, and contradictory data where found. "
            "The output should be comprehensive enough to inform a board presentation or grant application."
        )
    }
}

DATA_EMPHASIS_OPTIONS = {
    "Programs & Initiatives": {
        "label": "Focus on what peers are doing",
        "instruction": (
            "Emphasize qualitative findings: named programs, strategic initiatives, partnerships, "
            "implementation approaches, governance models, and organizational structures. "
            "Numbers should support the narrative, not lead it."
        )
    },
    "Quantitative Metrics": {
        "label": "Focus on numbers, benchmarks & thresholds",
        "instruction": (
            "Emphasize hard data: specific percentages, rates, scores, dollar amounts, timeframes, "
            "thresholds, benchmarks, rankings, and outcome measures. "
            "For every claim, find a number to support it. Include comparison tables with metric values. "
            "Highlight where peers meet, exceed, or fall below standard thresholds. "
            "Timeliness metrics, wait times, throughput rates, and performance targets are especially valuable."
        )
    },
    "Both - Full Picture": {
        "label": "Programs + metrics combined",
        "instruction": (
            "Provide equal weight to qualitative programs and quantitative metrics. "
            "For every initiative described, include the measurable outcomes. "
            "For every metric cited, explain the program or strategy behind it. "
            "Include threshold values, timeliness benchmarks, and performance targets alongside program descriptions."
        )
    }
}


# ============================================================
# 2. SESSION STATE INITIALIZATION
# ============================================================

def init_session_state():
    defaults = {
        "analysis_history": [],
        "chat_history": [],
        "analysis_done": False,
        "last_result_raw": "",
        "last_peer_data": "",
        "last_peer_list": "",
        "last_primary_focus": "",
        "last_secondary_focus": [],
        "last_topic": "",
        "last_depth": "Standard Analysis",
        "last_data_emphasis": "Both - Full Picture",
        "dynamic_followups": [],
        "sources": [],
        "generating_followups": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session_state()


# ============================================================
# 3. TERMINAL LOG HANDLER
# ============================================================

class StreamlitCallbackHandler:
    def __init__(self, container):
        self.container = container

    def on_step(self, step):
        with self.container:
            if hasattr(step, 'tool') and step.tool:
                st.markdown(f"**⚙️ AGENT >** `{step.tool}`")
                thought = getattr(step, 'thought', None)
                if thought:
                    st.code(thought[:500], language="text")


# ============================================================
# 4. FOCUS AREA CONTEXT BUILDER
# ============================================================

def build_focus_instruction(primary_focus, secondary_focus):
    """Build a clear hierarchical focus instruction for agents."""
    instruction = f'PRIMARY FOCUS (build everything around this): "{primary_focus}"\n'
    if secondary_focus:
        secondary_str = ", ".join(f'"{s}"' for s in secondary_focus)
        instruction += (
            f'SECONDARY FOCUS (enrich the analysis where directly relevant, do not derail): {secondary_str}\n'
            f'Rule: Secondary focus areas should appear as supporting context within primary focus sections, '
            f'not as standalone sections. Only include secondary insights if they materially relate to the '
            f'primary focus and the research topic.'
        )
    else:
        instruction += 'No secondary focus areas selected.'
    return instruction


# ============================================================
# 5. MEMORY CONTEXT BUILDER
# ============================================================

def build_memory_context():
    if not st.session_state.analysis_history:
        return ""
    lines = ["### Prior Analyses (Session Memory):"]
    for i, entry in enumerate(st.session_state.analysis_history):
        lines.append(
            f"- Run {i+1}: Topic='{entry['topic']}', "
            f"Primary Focus='{entry.get('primary_focus', '')}', "
            f"Secondary Focus='{entry.get('secondary_focus', '')}', "
            f"Peers={entry['hospitals']}. Summary: {entry['summary']}"
        )
    return "\n".join(lines)


# ============================================================
# 6. TOPIC-ANCHORED SCOPING INSTRUCTION (PATENT-GRADE)
# ============================================================

def build_scoping_instruction(topic, primary_focus, secondary_focus, data_emphasis_key, depth_key):
    """
    Topic-anchored scoping: include anything that illuminates the topic,
    exclude only what is genuinely irrelevant. This preserves rich supporting
    data (thresholds, timeliness, benchmarks) while keeping the memo focused.
    """
    depth_instr = DEPTH_OPTIONS[depth_key]["instruction"]
    data_instr = DATA_EMPHASIS_OPTIONS[data_emphasis_key]["instruction"]
    focus_instr = build_focus_instruction(primary_focus, secondary_focus)

    return f"""
RESEARCH PHILOSOPHY — TOPIC-ANCHORED SCOPING:
Your central anchor is the research topic: "{topic}"
Your primary strategic lens is: "{primary_focus}"

INCLUSION RULE: Include ANY data point, metric, benchmark, threshold, financial figure,
operational statistic, or qualitative finding IF it helps explain, measure, contextualize,
or improve performance on "{topic}". This includes:
- Timeliness metrics and wait time thresholds if they relate to "{topic}"
- Financial data if it funds, constrains, or enables "{topic}"
- Quality scores if they measure outcomes related to "{topic}"
- Staffing ratios if they affect delivery of "{topic}"
- Rankings if they reflect performance on "{topic}"
- Technology investments if they advance "{topic}"

EXCLUSION RULE: Exclude ONLY data that has NO connection to "{topic}" —
generic hospital statistics that neither explain nor illuminate the topic.
Ask yourself: "Does this help the reader understand how peers perform on '{topic}'?"
If yes, include it. If no, leave it out.

DEPTH INSTRUCTION:
{depth_instr}

DATA EMPHASIS INSTRUCTION:
{data_instr}

FOCUS HIERARCHY:
{focus_instr}
"""


# ============================================================
# 7. SOURCE EXTRACTOR
# ============================================================

def extract_sources(research_raw, topic):
    extractor_agent = Agent(
        role='Research Librarian',
        goal='Extract all sources from a research document with titles, URLs, and contribution summaries.',
        backstory=(
            'You are a meticulous research librarian. You extract every URL, publication, report, '
            'database, or named source from research documents. For each source, you provide a '
            'one-sentence summary of what it contributed. You never fabricate URLs.'
        ),
        tools=[],
        verbose=False
    )

    extractor_task = Task(
        description=(
            f'Extract ALL sources from this research document about "{topic}".\n\n'
            f'DOCUMENT:\n{research_raw[:6000]}\n\n'
            f'For each source, use EXACTLY this format:\n'
            f'SOURCE: [title or name]\n'
            f'URL: [full URL or "No URL available"]\n'
            f'CONTRIBUTION: [one sentence on what this source contributed]\n'
            f'---\n\n'
            f'If no sources found, write: NO_SOURCES_FOUND'
        ),
        agent=extractor_agent,
        expected_output='Numbered list of sources with SOURCE:, URL:, CONTRIBUTION: fields.'
    )

    crew = Crew(agents=[extractor_agent], tasks=[extractor_task], process=Process.sequential)
    result = crew.kickoff()
    return parse_sources(result.raw)


def parse_sources(raw_text):
    if "NO_SOURCES_FOUND" in raw_text:
        return []
    sources = []
    blocks = raw_text.strip().split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        source = {"title": "", "url": "", "contribution": ""}
        title_match = re.search(r'SOURCE:\s*(.+)', block)
        url_match = re.search(r'URL:\s*(.+)', block)
        contribution_match = re.search(r'CONTRIBUTION:\s*(.+)', block, re.DOTALL)
        if title_match:
            source["title"] = title_match.group(1).strip()
        if url_match:
            url = url_match.group(1).strip()
            source["url"] = url if url.startswith("http") else ""
        if contribution_match:
            source["contribution"] = contribution_match.group(1).strip()[:200]
        if source["title"] or source["url"]:
            sources.append(source)
    return sources


# ============================================================
# 8. DYNAMIC FOLLOW-UP QUESTION GENERATOR
# ============================================================

def generate_followup_questions(topic, primary_focus, secondary_focus, peer_list, memo_snippet):
    secondary_str = ", ".join(secondary_focus) if secondary_focus else "none"

    followup_agent = Agent(
        role='Strategic Research Advisor',
        goal=f'Generate 6 incisive follow-up questions about "{topic}".',
        backstory=(
            f'You help NCHS leadership go deeper on specific research topics. '
            f'Topic: "{topic}". Primary Focus: "{primary_focus}". '
            f'Secondary Focus: {secondary_str}. Peers: {peer_list}.\n'
            f'Snippet of completed analysis:\n{memo_snippet[:600]}'
        ),
        tools=[],
        verbose=False
    )

    followup_task = Task(
        description=(
            f'Generate exactly 6 follow-up questions for NCHS leadership about "{topic}".\n\n'
            f'Rules:\n'
            f'- All questions must be directly about "{topic}" through the lens of "{primary_focus}"\n'
            f'- Dig deeper into what was already found — no surface-level questions\n'
            f'- Mix: deeper data requests, implementation specifics, competitive gaps, '
            f'threshold comparisons, and NCHS-specific action items\n'
            f'- Questions should be specific enough that an agent can research them\n'
            f'- NO generic hospital questions unless directly tied to "{topic}"\n\n'
            f'Return ONLY a numbered list 1-6. One question per line. No headers or explanations.'
        ),
        agent=followup_agent,
        expected_output='Numbered list of 6 follow-up questions scoped to the research topic.'
    )

    crew = Crew(agents=[followup_agent], tasks=[followup_task], process=Process.sequential)
    result = crew.kickoff()

    lines = result.raw.strip().split("\n")
    questions = []
    for line in lines:
        line = line.strip()
        if line and len(line) > 10:
            cleaned = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            if cleaned:
                questions.append(cleaned)
    return questions[:6]


# ============================================================
# 9. FOLLOW-UP CHAT AGENT
# ============================================================

def run_followup(user_question):
    secondary_str = ", ".join(st.session_state.last_secondary_focus) if st.session_state.last_secondary_focus else "none"
    scoping = build_scoping_instruction(
        st.session_state.last_topic,
        st.session_state.last_primary_focus,
        st.session_state.last_secondary_focus,
        st.session_state.last_data_emphasis,
        st.session_state.last_depth
    )

    context = f"""
You are an expert healthcare strategist for Nicklaus Children's Hospital (NCHS).
You completed a benchmarking analysis on: "{st.session_state.last_topic}"

EXECUTIVE MEMO:
{st.session_state.last_result_raw}

RAW RESEARCH DATA:
{st.session_state.last_peer_data}

Peers: {st.session_state.last_peer_list}
Primary Focus: {st.session_state.last_primary_focus}
Secondary Focus: {secondary_str}

RECENT CHAT:
{chr(10).join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state.chat_history[-6:]])}

{scoping}
"""

    agent = Agent(
        role='NCHS Strategic Research Advisor',
        goal=f'Answer with precision and data: {user_question}',
        backstory=context,
        tools=[TavilySearchTool()],
        verbose=True,
        memory=True
    )

    task = Task(
        description=(
            f'Answer this question comprehensively:\n\n"{user_question}"\n\n'
            f'Requirements:\n'
            f'- Anchor everything to "{st.session_state.last_topic}"\n'
            f'- Include specific data: percentages, rates, thresholds, timelines, dollar amounts\n'
            f'- Name specific peer hospitals and their programs\n'
            f'- Include timeliness benchmarks and threshold values where they illuminate the topic\n'
            f'- Provide 2-3 concrete, actionable NCHS recommendations\n'
            f'- Use ## headers for structure\n'
            f'- NEVER use "[As above]" or any placeholder — write everything in full'
        ),
        agent=agent,
        expected_output=f'Complete, data-rich response about "{st.session_state.last_topic}". No placeholders.'
    )

    crew = Crew(
        agents=[agent], tasks=[task], process=Process.sequential,
        memory=True, embedder={"provider": "openai", "config": {"model": "text-embedding-3-small"}}
    )
    return crew.kickoff().raw


# ============================================================
# 10. UI — PAGE CONFIG & STYLING
# ============================================================

st.set_page_config(page_title="NCHS Intelligence Portal", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    /* Base font */
    html, body, [class*="css"] { font-family: 'Georgia', serif; }

    /* Title */
    h1 { 
        color: #003865 !important; 
        font-size: 1.8rem !important;
        border-bottom: 3px solid #00A0C6;
        padding-bottom: 0.5rem;
        margin-bottom: 1.5rem;
    }

    /* Section headers */
    h2, h3 { color: #003865 !important; }

    /* Sidebar background */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #003865 0%, #005b99 100%);
    }

    /* Sidebar — labels, markdown, captions: white text */
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stCaption p,
    section[data-testid="stSidebar"] .stCheckbox label,
    section[data-testid="stSidebar"] .stRadio label,
    section[data-testid="stSidebar"] h3 {
        color: white !important;
    }

    /* Sidebar — input/select interiors keep dark text on white bg */
    section[data-testid="stSidebar"] [data-baseweb="select"] [data-baseweb="tag"] span,
    section[data-testid="stSidebar"] [data-baseweb="select"] [class*="placeholder"],
    section[data-testid="stSidebar"] [data-baseweb="select"] [class*="singleValue"],
    section[data-testid="stSidebar"] [data-baseweb="select"] [class*="option"],
    section[data-testid="stSidebar"] input {
        color: #1a1a1a !important;
    }

    /* Primary focus badge */
    .primary-badge {
        background: #003865;
        color: white !important;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: bold;
        display: inline-block;
        margin: 2px;
    }
    .secondary-badge {
        background: #00A0C6;
        color: white !important;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        display: inline-block;
        margin: 2px;
    }

    /* Source cards */
    .source-card {
        border: 1px solid #e0e9f0;
        border-left: 4px solid #00A0C6;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 10px;
        background: #f8fbfd;
    }

    /* Follow-up question buttons */
    .stButton button {
        border: 1px solid #00A0C6 !important;
        color: #003865 !important;
        background: white !important;
        border-radius: 20px !important;
        font-size: 0.82rem !important;
        padding: 4px 14px !important;
        transition: all 0.2s;
    }
    .stButton button:hover {
        background: #003865 !important;
        color: white !important;
    }

    /* Depth & emphasis pills */
    .config-pill {
        background: #e8f4f9;
        border: 1px solid #00A0C6;
        color: #003865;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        display: inline-block;
        margin: 3px;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab"] {
        font-size: 0.9rem;
        font-weight: 600;
        color: #003865;
    }

    /* Divider color */
    hr { border-color: #e0e9f0 !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 11. SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown("### 🏥 NCHS Intelligence Portal")
    st.markdown("---")

    # Research Objective
    st.markdown("**📋 Research Objective**")
    research_topic = st.text_input(
        "What do you want to benchmark?",
        placeholder="e.g. Sepsis Care Protocols",
        label_visibility="collapsed"
    )

    st.markdown("---")

    # Peer Selection
    st.markdown("**🏦 Peer Institutions**")
    select_all = st.checkbox("Select All")
    selected_hospitals = st.multiselect(
        "Select peers",
        options=TOP_20_HOSPITALS,
        default=TOP_20_HOSPITALS if select_all else ["CHOP", "Boston Children's"],
        label_visibility="collapsed"
    )

    st.markdown("---")

    # Primary Focus (single, required) — use key to persist across reruns
    st.markdown("**🎯 Primary Focus** *(required)*")
    primary_focus = st.selectbox(
        "Primary focus",
        options=STRATEGIC_FOCUS_AREAS,
        key="primary_focus_select",
        label_visibility="collapsed"
    )

    # Secondary Focus (multi, optional) — exclude selected primary to avoid conflicts
    st.markdown("**➕ Secondary Focus** *(optional)*")
    secondary_options = [f for f in STRATEGIC_FOCUS_AREAS if f != primary_focus]
    # Filter out any stale secondary values that now match primary
    secondary_focus = st.multiselect(
        "Secondary focus",
        options=secondary_options,
        default=[
            v for v in st.session_state.get("secondary_focus_select", [])
            if v in secondary_options
        ],
        key="secondary_focus_select",
        label_visibility="collapsed"
    )
    if secondary_focus:
        st.caption(f"Enriching with: {', '.join(secondary_focus)}")

    st.markdown("---")

    # Analysis Depth
    st.markdown("**⚙️ Analysis Depth**")
    depth_key = st.radio(
        "Depth",
        options=list(DEPTH_OPTIONS.keys()),
        index=1,
        label_visibility="collapsed"
    )
    st.caption(DEPTH_OPTIONS[depth_key]["label"])

    st.markdown("---")

    # Data Emphasis
    st.markdown("**📊 Data Emphasis**")
    data_emphasis_key = st.radio(
        "Emphasis",
        options=list(DATA_EMPHASIS_OPTIONS.keys()),
        index=2,
        label_visibility="collapsed"
    )
    st.caption(DATA_EMPHASIS_OPTIONS[data_emphasis_key]["label"])

    st.markdown("---")

    # Session Memory
    st.markdown("**🧠 Session Memory**")
    if st.session_state.analysis_history:
        st.caption(f"{len(st.session_state.analysis_history)} run(s) stored")
        for i, entry in enumerate(st.session_state.analysis_history):
            with st.expander(f"Run {i+1}: {entry['topic'][:25]}..."):
                st.write(f"**Focus:** {entry.get('primary_focus', '')}")
                st.write(f"**Peers:** {entry['hospitals'][:60]}...")
                st.write(f"**Summary:** {entry['summary'][:150]}...")
        if st.button("🗑️ Clear All Memory"):
            for key in ["analysis_history", "chat_history", "dynamic_followups", "sources"]:
                st.session_state[key] = []
            st.session_state.analysis_done = False
            st.session_state.last_result_raw = ""
            st.session_state.last_peer_data = ""
            st.rerun()
    else:
        st.caption("No runs yet.")

    st.markdown("---")
    st.caption("NCHS Intelligence Portal · Professional")


# ============================================================
# 12. MAIN CONTENT AREA — HEADER
# ============================================================

st.title("🏥 NCHS Strategic Intelligence Portal")

# Show current config if analysis done
if st.session_state.analysis_done:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'<span class="config-pill">🎯 {st.session_state.last_primary_focus}</span>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<span class="config-pill">{st.session_state.last_depth}</span>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<span class="config-pill">{st.session_state.last_data_emphasis}</span>', unsafe_allow_html=True)


# ============================================================
# 13. LAUNCH BUTTON & VALIDATION
# ============================================================

col_btn, col_info = st.columns([1, 3])
with col_btn:
    run_button = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

if run_button:
    errors = []
    if not research_topic:
        errors.append("Please enter a research objective.")
    if not selected_hospitals:
        errors.append("Please select at least one peer institution.")
    if errors:
        for e in errors:
            st.error(e)
    else:
        peer_list = ", ".join(selected_hospitals)
        memory_context = build_memory_context()
        scoping_instruction = build_scoping_instruction(
            research_topic, primary_focus, secondary_focus,
            data_emphasis_key, depth_key
        )
        secondary_str = ", ".join(secondary_focus) if secondary_focus else "none selected"

        # ── Live stream container ──
        st.subheader("💻 Live Research Stream")
        terminal_container = st.container(border=True)
        handler = StreamlitCallbackHandler(terminal_container)

        with st.status("🤖 Intelligence Team Initializing...", expanded=True) as status:

            # ── RESEARCHER AGENT ──
            researcher = Agent(
                role='Senior Healthcare Intelligence Analyst',
                goal=(
                    f'Research "{research_topic}" across {peer_list} '
                    f'through the lens of "{primary_focus}".'
                ),
                backstory=(
                    f'You are the foremost expert in pediatric hospital competitive intelligence. '
                    f'You have spent 20 years benchmarking children\'s hospitals and you know that '
                    f'the most valuable insights come from connecting specific programs to measurable outcomes. '
                    f'You never produce vague summaries — every finding is anchored in a specific number, '
                    f'threshold, timeline, or named initiative. '
                    f'You are researching "{research_topic}" right now. '
                    f'You know that great research includes supporting context: if a peer\'s sepsis '
                    f'protocol has a 90-minute threshold, you find that number. If a care pathway '
                    f'reduced ALOS by 1.2 days, you find that number. '
                    f'IMPORTANT: For every fact, note the source URL or publication.\n\n'
                    f'{scoping_instruction}'
                    + (f'\n\nPRIOR RESEARCH CONTEXT:\n{memory_context}' if memory_context else '')
                ),
                tools=[TavilySearchTool()],
                verbose=True,
                memory=True
            )

            # ── WRITER AGENT ──
            writer = Agent(
                role='Executive Strategic Communications Director',
                goal=(
                    f'Produce a world-class executive memo on "{research_topic}" '
                    f'that NCHS leadership will act on immediately.'
                ),
                backstory=(
                    f'You are the most respected healthcare strategist in children\'s hospital leadership. '
                    f'Your memos have shaped $100M+ investment decisions. '
                    f'You write with clarity, authority, and precision. '
                    f'Your secret: you always connect peer data directly to NCHS opportunities. '
                    f'You NEVER write "[As above]", "[See above]", or any placeholder — '
                    f'every word is written in full. '
                    f'You know that a great memo shows both what peers are doing AND '
                    f'the specific numbers that prove it works. '
                    f'Your primary topic is "{research_topic}". '
                    f'Primary strategic lens: "{primary_focus}". '
                    f'Secondary context (where relevant): {secondary_str}.\n\n'
                    f'{scoping_instruction}'
                    + (f'\n\nPRIOR RESEARCH CONTEXT:\n{memory_context}' if memory_context else '')
                ),
                verbose=True,
                memory=True
            )

            # ── TASK 1: RESEARCH ──
            t1 = Task(
                description=(
                    f'Conduct comprehensive intelligence research on "{research_topic}" '
                    f'across: {peer_list}.\n\n'
                    f'PRIMARY DIRECTIVE: "{research_topic}" is your anchor. '
                    f'Everything you find must illuminate this topic.\n\n'
                    f'PRIMARY FOCUS: "{primary_focus}"\n'
                    f'SECONDARY FOCUS (enrich where relevant): {secondary_str}\n\n'
                    f'For each peer institution, research and document:\n'
                    f'1. Named programs, protocols, and initiatives related to "{research_topic}"\n'
                    f'2. Specific outcome metrics, rates, scores, and thresholds tied to "{research_topic}"\n'
                    f'3. Timeliness benchmarks, throughput targets, and performance thresholds\n'
                    f'4. Implementation details: timelines, costs, staffing, technology used\n'
                    f'5. Results achieved: before/after comparisons, improvement percentages\n'
                    f'6. Strategic investments and innovations in "{research_topic}"\n'
                    f'7. Any supporting context (financial, operational, quality) that directly '
                    f'explains performance on "{research_topic}"\n\n'
                    f'TOPIC-ANCHORED SCOPING:\n'
                    f'Include a data point if it answers: "How does this help us understand '
                    f'how [peer] performs on {research_topic}?"\n'
                    f'Exclude a data point if it has no connection to "{research_topic}".\n\n'
                    f'Note the source URL or publication for every major finding.\n\n'
                    f'{DEPTH_OPTIONS[depth_key]["instruction"]}\n'
                    f'{DATA_EMPHASIS_OPTIONS[data_emphasis_key]["instruction"]}'
                    + (f'\n\nBuild on prior research:\n{memory_context}' if memory_context else '')
                ),
                agent=researcher,
                expected_output=(
                    f'A comprehensive, data-rich intelligence report on "{research_topic}" '
                    f'covering all peer institutions. Includes named programs, specific metrics, '
                    f'thresholds, timeliness data, and source references. '
                    f'All findings tied to the research topic.'
                )
            )

            # ── TASK 2: WRITE MEMO ──
            focus_header = primary_focus
            if secondary_focus:
                focus_header += f" + {', '.join(secondary_focus)}"

            t2 = Task(
                description=(
                    f'Using the research provided, write a COMPLETE, FULLY WRITTEN '
                    f'Executive Strategic Memo for NCHS leadership.\n\n'
                    f'ABSOLUTE RULES:\n'
                    f'- Topic anchor: "{research_topic}" — every sentence serves this\n'
                    f'- NEVER write "[As above]", "[See above]", or ANY placeholder\n'
                    f'- Every section written in full — no shortcuts, no references to other sections\n'
                    f'- Include specific numbers, thresholds, and named programs throughout\n'
                    f'- Secondary focus ({secondary_str}) appears as enriching context, not standalone sections\n\n'
                    f'Topic: {research_topic}\n'
                    f'Primary Focus: {primary_focus}\n'
                    f'Secondary Focus: {secondary_str}\n'
                    f'Peers: {peer_list}\n\n'
                    f'WRITE ALL SECTIONS IN FULL:\n\n'
                    f'## Executive Summary\n'
                    f'4-5 sentences. Most critical findings about "{research_topic}". '
                    f'Lead with the most surprising or actionable insight. Include 2-3 key numbers.\n\n'
                    f'## Peer Benchmark: {research_topic}\n'
                    f'For each peer: their specific approach to "{research_topic}", '
                    f'named programs, key metrics, and standout results. '
                    f'Include a markdown comparison table with the most important metrics.\n\n'
                    f'## Performance Metrics & Thresholds\n'
                    f'Specific rates, scores, benchmarks, thresholds, and timeliness data '
                    f'that measure "{research_topic}" performance across peers. '
                    f'Identify best-in-class thresholds and industry standards.\n\n'
                    f'## Innovations & Strategic Investments\n'
                    f'What peers are building, funding, or piloting related to "{research_topic}". '
                    f'Include program names, dollar amounts, partnership details, and timelines.\n\n'
                    f'## NCHS Position: Gaps & Competitive Advantages\n'
                    f'Where NCHS leads and lags on "{research_topic}". '
                    f'Be specific — cite the peer data that reveals each gap or advantage.\n\n'
                    f'## Strategic Recommendations for NCHS\n'
                    f'5 prioritized, fully explained recommendations. Each must include:\n'
                    f'(a) The specific action\n'
                    f'(b) The peer evidence that supports it (name the hospital and the data)\n'
                    f'(c) The expected impact with estimated metrics where possible\n'
                    f'(d) Priority level: Immediate / 6-month / 12-month\n\n'
                    f'## Key Intelligence at a Glance\n'
                    f'10 bullet points. The most important stats, thresholds, and findings '
                    f'about "{research_topic}" from this entire analysis.\n\n'
                    f'Write for C-suite. Be authoritative. Every claim backed by data.'
                    + (f'\n\nPrior context:\n{memory_context}' if memory_context else '')
                ),
                agent=writer,
                context=[t1],
                expected_output=(
                    f'Complete executive memo on "{research_topic}". All 7 sections fully written. '
                    f'Rich with specific metrics, thresholds, named programs, and peer comparisons. '
                    f'5 prioritized recommendations with evidence and timelines. Zero placeholders.'
                )
            )

            # ── CREW KICKOFF ──
            crew = Crew(
                agents=[researcher, writer],
                tasks=[t1, t2],
                process=Process.sequential,
                memory=True,
                embedder={"provider": "openai", "config": {"model": "text-embedding-3-small"}},
                output_log_file="nchs_crew_log.txt",
                step_callback=handler.on_step
            )

            result = crew.kickoff()
            status.update(label="✅ Analysis Complete", state="complete")

        # ── SAVE TO SESSION STATE ──
        st.session_state.last_result_raw = result.raw
        st.session_state.last_peer_data = result.tasks_output[0].raw
        st.session_state.last_peer_list = peer_list
        st.session_state.last_primary_focus = primary_focus
        st.session_state.last_secondary_focus = secondary_focus
        st.session_state.last_topic = research_topic
        st.session_state.last_depth = depth_key
        st.session_state.last_data_emphasis = data_emphasis_key
        st.session_state.analysis_done = True
        st.session_state.chat_history = []

        summary_snippet = (
            result.raw[:300].replace("\n", " ") + "..."
            if len(result.raw) > 300 else result.raw
        )
        st.session_state.analysis_history.append({
            "topic": research_topic,
            "primary_focus": primary_focus,
            "secondary_focus": ", ".join(secondary_focus) if secondary_focus else "",
            "hospitals": peer_list[:80],
            "summary": summary_snippet
        })

        # ── POST-PROCESSING ──
        with st.spinner("📚 Extracting sources..."):
            st.session_state.sources = extract_sources(
                result.tasks_output[0].raw, research_topic
            )

        with st.spinner("💡 Generating follow-up questions..."):
            st.session_state.dynamic_followups = generate_followup_questions(
                research_topic, primary_focus, secondary_focus, peer_list, result.raw
            )

        st.rerun()


# ============================================================
# 14. RESULTS DISPLAY
# ============================================================

if st.session_state.analysis_done:

    tab1, tab2, tab3 = st.tabs([
        "📝 Executive Memo & Follow-Up",
        "🔍 Raw Research Data",
        "📚 Sources & Resources"
    ])

    # ── TAB 1: MEMO + FOLLOW-UP ──
    with tab1:

        # Memo health check
        if (
            "[As above]" in st.session_state.last_result_raw
            or len(st.session_state.last_result_raw) < 200
        ):
            st.warning(
                "⚠️ The memo appears incomplete or contains placeholder text. "
                "Try re-running the analysis."
            )

        # Focus badges
        st.markdown(
            f'<span class="primary-badge">🎯 {st.session_state.last_primary_focus}</span>',
            unsafe_allow_html=True
        )
        for sf in st.session_state.last_secondary_focus:
            st.markdown(f'<span class="secondary-badge">+ {sf}</span>', unsafe_allow_html=True)

        st.markdown("---")

        # The memo
        st.markdown(st.session_state.last_result_raw)

        # ── FOLLOW-UP QUESTIONS (below memo) ──
        if st.session_state.dynamic_followups:
            st.markdown("---")
            st.markdown(
                f"### 💡 Suggested Follow-Up Questions",
                help="These questions are scoped to your research topic and generated from the analysis above."
            )
            st.caption(f"Scoped to: *{st.session_state.last_topic}* · *{st.session_state.last_primary_focus}*")

            cols = st.columns(2)
            for i, suggestion in enumerate(st.session_state.dynamic_followups):
                with cols[i % 2]:
                    if st.button(f"❓ {suggestion}", key=f"memo_suggestion_{i}", use_container_width=True):
                        st.session_state.chat_history.append({"role": "user", "content": suggestion})
                        with st.spinner(f"🤖 Researching: {suggestion[:60]}..."):
                            response = run_followup(suggestion)
                        st.session_state.chat_history.append({"role": "assistant", "content": response})
                        st.rerun()

        # ── CHAT HISTORY (below follow-ups) ──
        if st.session_state.chat_history:
            st.markdown("---")
            st.markdown("### 💬 Follow-Up Research")
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        # ── FREE-FORM CHAT INPUT ──
        st.markdown("---")
        if prompt := st.chat_input(
            f"Ask anything about {st.session_state.last_topic}...",
            key="main_chat_input"
        ):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("🤖 Researching..."):
                    response = run_followup(prompt)
                st.markdown(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.rerun()

    # ── TAB 2: RAW RESEARCH ──
    with tab2:
        st.subheader("🔍 Raw Research Intelligence")
        st.caption(
            "This is the unprocessed output from the research agent — "
            "the full data before the writer agent synthesized it into the memo."
        )
        st.code(st.session_state.last_peer_data, language="markdown")

    # ── TAB 3: SOURCES ──
    with tab3:
        st.subheader(f"📚 Research Sources")
        st.caption(
            f"Sources identified by the research agent for: "
            f"*{st.session_state.last_topic}* across {st.session_state.last_peer_list}"
        )

        if not st.session_state.sources:
            st.info(
                "No external sources were extracted from this analysis. "
                "This may occur when the agent synthesized primarily from training knowledge. "
                "Running a Deep Dive analysis typically surfaces more citable sources."
            )
        else:
            st.markdown(f"**{len(st.session_state.sources)} source(s) identified**")
            st.divider()

            for i, source in enumerate(st.session_state.sources):
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        title = source.get("title") or f"Source {i + 1}"
                        st.markdown(f"**{title}**")
                        if source.get("contribution"):
                            st.caption(f"📌 {source['contribution']}")
                    with col2:
                        url = source.get("url", "")
                        if url:
                            st.link_button("🔗 Open", url, use_container_width=True)
                        else:
                            st.caption("No URL")