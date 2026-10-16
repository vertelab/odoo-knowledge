# -*- coding: utf-8 -*-
{
    'name': 'Knowledge: Document Law AI',
    'version': '18.0.1.0.0',
    'summary': 'OKF bridge for document.law + a law-reading agent for the general assistant',
    'category': 'Hidden',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se',
    'license': 'AGPL-3',
    'description': """
        Bridge module for Swedish statutes and the AI coworker.

        OKF INDEXING: puts `ai.okf.mixin` on `document.law` so that the
        laws become OKF concepts.

        WHY: `document_law` is in active production use — thousands of law
        records refreshed daily from the Riksdag RSS feed — but nothing can
        read them. The records are plain rows: a designation, a department,
        a publication date and a body of legal text. Finding the law that
        applies to a question is manual work. This bridge makes the laws
        indexable, so a law can be found by meaning and not only by its
        designation.

        MODEL CHOICE: `document.law` is its own model. It merely *depends*
        on `document_page`; it does not inherit it. Bridging `document.page`
        again would be a second bridge on a model that already has one
        (`knowledge_document_ai`) and would index nothing about the laws.
        The bridge therefore inherits `document.law`, with its own
        `document_law_okf_tag_rel` table.

        LAW AGENT: an `ai.agent` "Lag-specialist" with a skill and three
        tools that let the general assistant find, read and interpret
        Swedish statutes in the context of the company asking:

          - `law_search`    — free text, designation, department, date range
          - `law_get`       — one law's text (not raw HTML)
          - `law_interpret` — the law's text plus the company's context

        The interpretation is grounded in `ai.company.memory`
        (`build_system_prompt_block` + `search_for_company`), so it is
        stated in terms of the company's business rather than being a
        generic restatement of the statute. The tool returns context plus
        law text; the agent does the interpreting — the tool never calls an
        LLM itself, which keeps it testable and keeps the reasoning inside
        the skill that constrains it.

        NO LEGAL ADVICE: the skill states that the agent explains what a law
        requires and what it implies for the company, but does not determine
        compliance and says so when asked. An agent that answers "yes, you
        comply" has made a legal determination it cannot make.

        ATTACHMENT: the agent is attached to Allmän assistent
        (`ai_agent_core.coworker_default_assistent`) as a member,
        additively. The link is made from `data/law_agent_attach.xml` — a
        `<function>` calling `document.law._ensure_agent_attachment()`,
        placed outside any noupdate block so it runs on install AND on
        upgrade. The method resolves the coworker with
        `raise_if_not_found=False`, so the module installs whether or not
        the assistant exists. Nothing is added to `ai_agent_core`: an
        installation without `document_law` carries no part of this.

        AUTOINSTALL: the module installs automatically as soon as both
        `ai_agent_core` and `document_law` are present. A law that cannot
        become knowledge is a law nobody finds — the bridge should not be a
        choice.
    """,
    'depends': [
        'ai_agent_core',
        'document_law',
    ],
    'data': [
        'data/okf_artifact_types_law.xml',
        'data/okf_debug_actions.xml',
        'data/law_skills.xml',
        'data/law_tools.xml',
        'data/law_agents.xml',
        'data/law_agent_attach.xml',
    ],
    'demo': [],
    'application': False,
    'installable': True,
    'auto_install': True,
}
