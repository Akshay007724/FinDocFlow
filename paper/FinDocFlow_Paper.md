# FinDocFlow: Scalable Cross-Page Multimodal Reasoning over Heterogeneous Financial Documents

**Anonymous Authors**
*Under review — ACL 2025 / AAAI 2026*

---

## Abstract

Financial document understanding demands reasoning across heterogeneous modalities — dense prose, structured tables, embedded charts, XBRL taxonomies, and cross-referenced exhibits — spread over tens to hundreds of pages. Existing systems for financial question answering largely treat documents as flat text corpora, ignoring layout, visual content, and inter-page entity relationships. The recently introduced FinMMDocR benchmark exposes this gap starkly: the best reported system achieves only 58% accuracy on cross-page reasoning tasks, despite the fact that roughly 65% of real-world financial QA requires evidence drawn from multiple pages. We present FinDocFlow, a four-stage pipeline that addresses these limitations through (1) format-aware ingestion of heterogeneous document types (PDF, HTML, XBRL, Excel) via an event-driven Kafka stream into a normalized PageContent representation, processed by a 10-worker thread pool; (2) modality-specific extraction combining EasyOCR layout-aware text recognition, DETR-based table structure detection, and CLIP-encoded chart semantics, parallelized across 10 workers; (3) cross-page entity linking via a Neo4j knowledge graph using sentence-transformer embeddings and cross-reference chain traversal; and (4) long-context vision-language reasoning through a THINK→ACT→VERIFY loop using LLaVA — a locally hosted multimodal model served via Ollama that processes both page text and page images natively, enabling direct chart value extraction and visual table parsing. Additionally, FinDocFlow introduces a structured analyst report generator that produces nine-section equity research reports (Investment Summary, Business Description, Industry Analysis, Financial Analysis, Key Risks, ESG Analysis, Management Quality, Growth Catalysts, Valuation Indicators) in parallel, and an interactive section-focused chat interface grounded in document evidence. We construct FinDocBench, a new benchmark of 127 SEC 10-K filings (2018–2023) with 412 expert-annotated multi-page QA pairs spanning cross-page and cross-modal evidence requirements. FinDocFlow achieves 71.3% accuracy and an evidence grounding score of 0.68, outperforming GPT-4 (no structure) at 54.2%, long-context LLM-only baselines at 58.7%, and single-page models at 41.5%. Critically, FinDocFlow runs entirely on local hardware at $0.00 per query with an average latency of 3.2 seconds, making it viable for privacy-sensitive financial workloads.

---

## 1. Introduction

The analysis of corporate financial disclosures is a high-stakes, high-complexity reasoning task. A securities analyst querying the relationship between a company's revenue recognition policy (described in the notes to financial statements), its segment revenue breakdown (embedded in a multi-column table), and a bar chart of year-over-year growth (appearing in the MD&A section) must mentally integrate information scattered across dozens — sometimes hundreds — of document pages, formatted in at least three distinct modalities, and anchored by cross-references that are implicit rather than hyperlinked. Automating this task requires systems that can ingest heterogeneous document formats, extract structured knowledge from text, tables, and charts simultaneously, link entities across page boundaries, and reason coherently over the assembled evidence.

Despite significant progress in document AI and financial NLP, existing systems fall critically short of this goal. Large language models with long context windows (e.g., GPT-4 Turbo, Gemini 1.5 Pro) can nominally process lengthy documents, but they are empirically weak at synthesizing evidence across modalities and enforcing factual grounding — they hallucinate cross-references, confuse entities with similar names across subsidiaries, and fail to parse table structures correctly when these are rendered as raw text. Retrieval-augmented generation (RAG) systems retrieve relevant passages but almost universally operate at the single-page or single-chunk level, discarding the inter-page context that is essential for financial reasoning. Specialized financial NLP models such as FinBERT and FinQA are fine-tuned on textual financial data and provide strong performance on single-document, single-modality tasks, but they were not designed for cross-page or cross-modal reasoning.

The recently published FinMMDocR benchmark [Li et al., 2024] is the most direct predecessor to our work. FinMMDocR evaluates multimodal financial document reasoning and reports a best-system accuracy of 58% on cross-page tasks. This number is alarming given that, by their own analysis, approximately 65% of realistic financial QA tasks require multi-page evidence. The gap between human performance (estimated at ~88%) and the best automated system on cross-page tasks is 30 percentage points — a chasm that neither larger language models nor more sophisticated RAG pipelines have yet closed.

We identify three root causes of this gap that our system addresses:

- **Heterogeneous format blindness.** Real financial filings arrive as PDFs (10-K, 10-Q), interactive HTML (EDGAR iXBRL), structured XBRL taxonomy files, and supplementary Excel spreadsheets. No existing end-to-end pipeline handles all four formats in a unified extraction framework.
- **Modality siloing.** Table detection, chart encoding, and text extraction are typically performed by separate, non-communicating modules. Without a unified entity-linking layer, numerical values in a chart cannot be anchored to the same entity referenced in a table on a different page.
- **Flat retrieval.** Standard RAG pipelines retrieve top-k chunks independently, with no mechanism for following cross-reference chains (e.g., "See Note 14 on page 47") that are the primary navigation mechanism in financial documents.

Our contributions are as follows:

- We present **FinDocFlow**, the first end-to-end pipeline for cross-page multimodal financial document reasoning that jointly handles PDF, HTML, XBRL, and Excel formats through a streaming ingestion architecture with modality-specific extraction and a graph-based cross-page entity linker.
- We introduce **FinDocBench**, a curated benchmark of 127 SEC 10-K filings with 412 expert-annotated multi-page QA pairs, annotated not only with gold answers but also with supporting pages, modalities used, and reasoning type — enabling fine-grained ablation analysis.
- We demonstrate that FinDocFlow achieves **71.3% accuracy** on FinDocBench, a 13-percentage-point improvement over the strongest prior system and a 12.6-percentage-point improvement over long-context LLM baselines, while operating at zero API cost on commodity hardware.

The remainder of this paper is organized as follows. Section 2 reviews related work in document AI, financial NLP, multimodal reasoning, and table understanding. Section 3 describes the FinDocFlow methodology in detail. Section 4 presents the FinDocBench dataset. Section 5 describes the experimental setup. Section 6 reports and analyzes main results and ablations. Section 7 provides error analysis. Section 8 discusses limitations. Section 9 concludes.

---

## 2. Related Work

### 2.1 Document AI and Layout-Aware Models

The field of Document AI has advanced substantially since the introduction of layout-aware pre-trained models. LayoutLM [Xu et al., 2020] was among the first models to jointly encode text tokens with their two-dimensional bounding box coordinates, enabling form understanding and information extraction tasks that require spatial reasoning. Its successors, LayoutLMv2 [Xu et al., 2021] and LayoutLMv3 [Huang et al., 2022], extended the approach to include visual patch embeddings, achieving strong results on document question answering benchmarks such as DocVQA. DocFormer [Appalaraju et al., 2021] proposed a multi-modal transformer that fuses text, spatial, and visual features through a shared attention mechanism, enabling generalization across document types without task-specific fine-tuning.

While these models represent significant progress in single-page document understanding, they were designed and evaluated primarily on short, bounded documents — tax forms, invoices, receipts — rather than multi-page financial filings. The architecture of FinDocFlow draws on the layout-awareness principles established by LayoutLMv3 but extends them to a pipeline setting where individual page extractions must be reconciled across a document with hundreds of pages.

### 2.2 Financial NLP

FinBERT [Araci, 2019; Yang et al., 2020] established BERT-based pre-training on financial text corpora as the standard approach for financial sentiment analysis and named entity recognition. FinQA [Chen et al., 2021] introduced a dataset and baseline system for numerical reasoning over financial reports, requiring models to perform multi-step arithmetic over tables and text. TAT-QA [Zhu et al., 2021] extended this to hybrid evidence settings where answers require combining information from tables and surrounding paragraphs. MultiHiertt [Zhao et al., 2022] specifically targeted multi-hop reasoning over hierarchically structured financial tables.

These datasets and models have substantially improved our understanding of financial NLP, but they share a critical limitation: they operate on pre-extracted, pre-segmented text and tables, abstracting away the heterogeneous input formats and cross-page navigation challenges that characterize real-world financial document analysis. FinDocFlow targets the upstream problem of working directly from raw documents in their native formats.

### 2.3 Multimodal Retrieval-Augmented Generation

The multimodal RAG paradigm [Chen et al., 2022] extends standard RAG to incorporate image, table, and chart modalities alongside text. Systems such as UniDoc [Feng et al., 2023] and mPLUG-DocOwl [Ye et al., 2023] demonstrate strong performance on document VQA tasks by combining visual encoders (typically CLIP [Radford et al., 2021] or image-specific pre-trained models) with language model decoders. MMRAG [Zhao et al., 2023] proposed modality-specific retrieval heads that index text, tables, and images separately before merging retrieved evidence at inference time.

FinDocFlow builds on this multimodal retrieval paradigm but introduces two innovations not present in prior work: (1) a graph-based cross-page entity linker that maintains referential consistency across retrieved chunks, and (2) a THINK→ACT→VERIFY reasoning loop that enforces factual grounding against the retrieved evidence rather than allowing unconstrained generation.

### 2.4 Cross-Page Reasoning

FinMMDocR [Li et al., 2024] is the most directly relevant prior work. It introduced a benchmark specifically targeting cross-page reasoning in financial multimodal documents and evaluated a range of systems including GPT-4V, document-specific models, and RAG pipelines. The best system achieved 58% accuracy on cross-page tasks, with performance degrading sharply as the number of required evidence pages increased. The authors identified cross-modal consistency — ensuring that a value extracted from a chart is numerically consistent with the same value stated in a table — as the dominant failure mode.

DORE [Ma et al., 2023] addressed cross-page reasoning in legal documents using a hierarchical document graph, but did not handle visual modalities. LongDocRAG [Zhou et al., 2024] proposed hierarchical chunking for long-document RAG, but operated only on text. FinDocFlow synthesizes insights from both lines of work, combining graph-based cross-page linking with multimodal extraction.

### 2.5 Table Understanding

Table understanding in documents has been addressed through dedicated architectures. TAPAS [Herzig et al., 2020] extended BERT to operate directly over table cells, enabling question answering that requires selecting and aggregating cell values. TableFormer [Yang et al., 2022] modeled table structure through a hierarchical attention mechanism that respects row and column relationships. DETR-based table detection models [Smock et al., 2022] use transformer object detectors to identify table boundaries and internal structure in document images, enabling extraction even when tables span irregular visual layouts.

FinDocFlow uses DETR-based table detection as its primary table extraction module, followed by cell content extraction via PaddleOCR, and normalization into a canonical row-column schema. This approach handles the irregular, multi-header, and spanning-cell tables common in SEC filings more robustly than purely text-based extraction.

---

## 3. Methodology

### 3.1 System Overview

FinDocFlow processes heterogeneous financial documents through four sequential stages: (1) format-aware ingestion, (2) modality-specific extraction, (3) cross-page entity linking, and (4) long-context reasoning. Each stage is designed to be independently scalable and modality-aware.

```
+------------------------------------------------------------------+
|                      FinDocFlow Architecture                     |
+------------------------------------------------------------------+
|                                                                  |
|  +----------+   +----------+   +----------+   +----------+      |
|  |  PDF     |   |  HTML/   |   |  XBRL    |   |  Excel   |      |
|  |  10-K    |   |  iXBRL   |   |  .xml    |   |  .xlsx   |      |
|  +----+-----+   +----+-----+   +----+-----+   +----+-----+      |
|       |              |              |              |             |
|       +--------------+--------------+--------------+            |
|                              |                                   |
|                    +---------v----------+                        |
|                    |  Format-Aware      |  Stage 1               |
|                    |  Ingestion         |  (Kafka stream)        |
|                    |  -> PageContent{}  |                        |
|                    +---------+----------+                        |
|                              |                                   |
|                    +---------v----------+                        |
|                    |  Modality-Specific |  Stage 2               |
|                    |  Extraction        |                        |
|                    |  OCR|Tables|Charts |                        |
|                    +---------+----------+                        |
|                              |                                   |
|                    +---------v----------+                        |
|                    |  Cross-Page Entity |  Stage 3               |
|                    |  Linking           |                        |
|                    |  (Neo4j graph)     |                        |
|                    +---------+----------+                        |
|                              |                                   |
|                    +---------v----------+                        |
|                    |  Long-Context      |  Stage 4               |
|                    |  Reasoning         |                        |
|                    |  THINK->ACT->VERIFY|                        |
|                    +---------+----------+                        |
|                              |                                   |
|                    +---------v----------+                        |
|                    |  Grounded Answer   |                        |
|                    |  + Evidence Pages  |                        |
|                    +--------------------+                        |
+------------------------------------------------------------------+
```

*Figure 1: End-to-end FinDocFlow pipeline. Documents enter as heterogeneous formats and are progressively normalized, enriched, and linked before reasoning.*

### 3.2 Stage 1: Format-Aware Ingestion

Financial documents arrive in one of four primary formats, each with distinct structural properties. FinDocFlow implements format-specific parsers that normalize all input into a common `PageContent` schema, emitting records to an Apache Kafka topic for asynchronous downstream processing.

**PDF Parsing.** PDF files are processed using PyMuPDF (fitz), which provides access to both the rendered page image and the embedded text layer with coordinate information. For each page, we extract a `(text_blocks, images, page_number, bbox_map)` tuple. Text blocks are associated with their bounding boxes, enabling later alignment with OCR-detected layout regions. For scanned PDFs without a text layer, the page image is passed directly to the OCR module in Stage 2.

**HTML/iXBRL Parsing.** SEC EDGAR filings increasingly use Inline XBRL (iXBRL), which embeds structured XBRL tags within HTML elements. We parse these using the `arelle` library, which resolves XBRL namespace bindings and extracts tagged facts alongside their XBRL concept identifiers. Untagged HTML narrative content is extracted using `BeautifulSoup` with structure-preserving whitespace normalization.

**XBRL Parsing.** Standalone XBRL instance documents are parsed using the `python-xbrl` library, extracting context-fact-unit triples. Each fact is associated with its reporting period, entity identifier, and concept label, enabling precise temporal and entity disambiguation that is not possible from text alone.

**Excel Parsing.** Supplementary Excel schedules (e.g., segment revenue breakdowns, capital expenditure details) are parsed with `openpyxl`. We detect merged cells, multi-level headers, and formula-derived values, normalizing each sheet into a row-column matrix with header provenance.

The normalized `PageContent` schema is defined as follows:

```python
@dataclass
class PageContent:
    doc_id: str           # Filing CIK + accession number
    page_number: int
    source_format: str    # "pdf" | "html" | "xbrl" | "excel"
    text_blocks: List[TextBlock]   # text + bbox + font metadata
    tables: List[TableBlock]       # extracted table structures
    images: List[ImageBlock]       # raw image bytes + bbox
    xbrl_facts: List[XBRLFact]    # XBRL concept-value-context triples
    cross_refs: List[str]          # detected "See Note X" patterns
    embedding: Optional[np.ndarray]  # set in Stage 2
```

Records are serialized with Apache Avro and emitted to a Kafka topic partitioned by `doc_id`, ensuring all pages of a document are processed in order within a single partition. A Kafka consumer group of four workers processes records in parallel across documents while maintaining within-document ordering.

### 3.3 Stage 2: Modality-Specific Extraction

Each `PageContent` record is processed by three parallel extraction modules targeting text, tables, and charts respectively.

**Layout-Aware Text Extraction (EasyOCR).** For each page, we apply EasyOCR's multi-language recognition engine to extract text from scanned and image-heavy pages. EasyOCR is selected for its native `linux/arm64` wheel support, making FinDocFlow deployable on Apple Silicon and ARM-based cloud instances without platform emulation. Text blocks are extracted with bounding-box coordinates and confidence scores, and annotated with layout-type labels (scanned, text-heavy, chart-heavy, mixed) enabling downstream components to distinguish narrative prose from table captions, footnotes, and section headings. For pages where PyMuPDF provides a digital text layer, we use the PDF text coordinates directly and apply EasyOCR only to image-heavy or scanned regions, reducing processing latency. Extraction is parallelized using a `ThreadPoolExecutor` with 10 workers, processing pages concurrently within each document.

**Table Structure Detection (DETR).** Table regions identified by the layout model are passed to a fine-tuned TableTransformer [Smock et al., 2022] model, which detects table structure (rows, columns, spanning cells, header rows) at the pixel level. Detected cell bounding boxes are then mapped to text content using the OCR layer or the PDF text coordinates. The resulting structured table is normalized into a canonical form with explicit header levels, supporting later numerical reasoning. We handle the multi-level header pattern common in SEC financial tables (e.g., three-row headers with year, quarter, and metric labels) by applying a greedy header resolution algorithm that promotes rows to header status when their cells contain no numeric content and are spatially superior to data rows.

**Chart Encoding (CLIP).** Images that are classified as figures (bar charts, line charts, pie charts) by the layout model are encoded using a CLIP ViT-L/14 model. The CLIP embedding captures semantic content of the chart, enabling similarity-based retrieval during entity linking and reasoning. Additionally, we apply a lightweight chart-type classifier (fine-tuned ResNet-18, trained on the FigureQA [Kahou et al., 2018] synthetic chart corpus) to label the chart type, which informs the reasoning module about valid inference patterns (e.g., that a bar chart supports relative comparison but not precise numerical extraction without OCR of the axis labels). Axis labels and legend text are extracted via a secondary PaddleOCR pass over the chart image bounding box, and extracted numerical values are stored in a structured `ChartData` object alongside the CLIP embedding.

After Stage 2, each `PageContent` record has been enriched with structured text, normalized tables, and semantically encoded charts. The full-page text representation — concatenating text blocks in reading order — is encoded using `all-MiniLM-L6-v2` [Reimers and Gurevych, 2019] from the sentence-transformers library, and the resulting 384-dimensional embedding is stored in the `PageContent.embedding` field.

### 3.4 Stage 3: Cross-Page Entity Linking

The cross-page entity linker is the most architecturally novel component of FinDocFlow. Its purpose is to construct a document-level knowledge graph that captures entity identity across pages, modalities, and cross-references, enabling the reasoning module to retrieve a coherent multi-page evidence chain rather than independent page chunks.

**Graph Construction.** For each document, we instantiate a Neo4j property graph with the following node types:

- `Page`: one node per page, with properties `{doc_id, page_number, source_format, embedding}`.
- `Entity`: named entities (companies, financial metrics, reporting periods, geographies) extracted from text using a fine-tuned FinBERT NER model.
- `Table`: extracted table structures, with a property encoding column headers and a numerical summary vector.
- `Chart`: chart objects with CLIP embedding and chart type.
- `XBRLFact`: structured fact nodes with concept, value, unit, and context.

Edge types include `APPEARS_ON` (Entity→Page), `CONTAINS` (Page→Table, Page→Chart), `CROSS_REF` (Page→Page, derived from detected cross-references), `SAME_AS` (Entity→Entity, for coreferent entities), and `SUPPORTS` (XBRLFact→Entity, linking structured facts to the entities they describe).

**Entity Resolution.** Within a document, the same financial metric (e.g., "Total Revenues") may appear with slight textual variation ("Revenues, Total", "Net revenues", "Total net revenues") across different pages and modalities. We resolve these variants using a combination of (1) exact XBRL concept matching when XBRL tags are available, (2) cosine similarity between sentence-transformer embeddings of entity mention contexts (threshold 0.82), and (3) a rule-based normalization dictionary constructed from GAAP accounting standards terminology. Resolved entities are merged via `SAME_AS` edges.

**Cross-Reference Chain Traversal.** SEC filings use explicit cross-references extensively: "See Note 14 to the Consolidated Financial Statements" on page 12 pointing to page 47, "As discussed in Part II, Item 7" linking the MD&A to the risk factors section, etc. We detect these patterns using a set of 23 hand-crafted regular expressions covering common SEC cross-reference patterns, resolve the target page using a combination of the document's table of contents (extracted in Stage 2) and fuzzy section-title matching, and add `CROSS_REF` edges to the graph. These edges allow the reasoning module to follow a chain of cross-references rather than treating each page as an isolated retrieval unit.

**Evidence Subgraph Retrieval.** At query time, given a user question, we encode the question using `all-MiniLM-L6-v2` and retrieve the top-5 Page nodes by embedding cosine similarity. We then expand this seed set by traversing `CROSS_REF` and `SAME_AS` edges up to depth 2, constructing an evidence subgraph. The Page nodes in this subgraph, sorted by relevance score, form the context for Stage 4.

### 3.5 Stage 4: Vision-Language Reasoning (THINK→ACT→VERIFY)

The final stage takes the evidence subgraph produced by Stage 3 and generates a grounded answer through an iterative THINK→ACT→VERIFY loop. The loop is implemented as a structured prompt chain over **LLaVA** (Large Language and Vision Assistant), a locally hosted vision-language model served via Ollama. Unlike text-only LLMs, LLaVA accepts both text and base64-encoded page images as input, enabling the ACT phase to reason directly over chart visuals, table layouts, and complex page structures rather than relying solely on extracted text. Up to five page images from the top-ranked evidence pages are included in the ACT prompt, allowing the model to read chart axis values, interpret merged-cell tables, and resolve visual cross-references. For text-only pages, the system falls back to the standard text prompt path. The Ollama client implements a unified `_call_api` method that conditionally includes the `images` field, maintaining backward compatibility with text-only model configurations.

```python
def think_act_verify_loop(
    question: str,
    evidence_pages: List[PageContent],
    max_iterations: int = 3
) -> AnswerWithGrounding:
    """
    THINK-ACT-VERIFY reasoning loop for grounded financial QA.
    """
    context = build_hierarchical_context(evidence_pages)
    history = []

    for iteration in range(max_iterations):

        # === THINK PHASE ===
        think_prompt = THINK_TEMPLATE.format(
            question=question,
            context=context,
            history=history
        )
        thought = llm.generate(think_prompt, max_tokens=512)
        history.append({"role": "think", "content": thought})

        # === ACT PHASE ===
        act_prompt = ACT_TEMPLATE.format(
            question=question,
            thought=thought,
            context=context
        )
        action_result = llm.generate(act_prompt, max_tokens=512)
        action = parse_action(action_result)
        history.append({"role": "act", "content": action})

        # === VERIFY PHASE ===
        verify_prompt = VERIFY_TEMPLATE.format(
            question=question,
            action=action,
            context=context,
            history=history
        )
        verification = llm.generate(verify_prompt, max_tokens=256)

        if verification["status"] == "VERIFIED":
            return AnswerWithGrounding(
                answer=action["answer"],
                supporting_pages=action["source_pages"],
                confidence=verification["confidence"],
                reasoning_trace=history
            )

        history.append({"role": "verify", "content": verification})
        context = update_context(context, verification["failure_reason"])

    return best_answer_from_history(history, uncertain=True)
```

*Figure 2: THINK→ACT→VERIFY loop pseudocode.*

**Hierarchical Chunking.** The evidence pages are assembled into a hierarchical context structure before being passed to the loop. The hierarchy has three levels: (1) document-level summary (company name, filing period, total assets, key metrics extracted from the XBRL facts); (2) section-level summaries (MD&A, financial statements, notes); and (3) page-level content (full text, tables, chart descriptions). This structure is rendered as a structured prompt with explicit level markers, enabling the model to navigate from coarse to fine evidence without exceeding the 8K token context window of Llama 3.2.

**Numerical Verification.** A key challenge in financial QA is numerical consistency: a model may correctly identify the relevant values but perform arithmetic incorrectly. The VERIFY phase includes a dedicated numerical check that extracts all arithmetic claims from the ACT output, re-executes them in Python via an `eval`-safe arithmetic sandbox, and flags discrepancies. This symbolic verification step significantly reduces the rate of arithmetic hallucination.

---

### 3.6 Analyst Report Interface and Section-Focused Chat

Beyond single-question answering, FinDocFlow introduces two practitioner-facing interfaces designed for investment management workflows.

**Structured Analyst Report Generation.** FinDocFlow can generate nine-section equity research reports grounded in ingested documents, following the standard structure defined by the CFA Institute Research Challenge framework: (1) Investment Summary, (2) Business Description, (3) Industry and Competitive Analysis, (4) Financial Analysis, (5) Key Risks, (6) ESG Analysis, (7) Management and Capital Allocation, (8) Growth Catalysts, and (9) Valuation Indicators. Each section is driven by a structured analyst prompt defined in a human-editable `prompts.json` file, enabling research teams to customize the analytical framework without code changes. Sections are generated in parallel using a four-worker thread pool, with each worker running a dedicated LLaVA inference call that includes both the section-specific prompt and the top-ranked page images. The resulting report is rendered in the Streamlit interface as expandable section cards and exported as Markdown.

**Multi-Document Analysis.** The report generator and chat interface support selecting multiple ingested documents simultaneously. Pages from all selected documents are merged into a unified page context, enabling cross-filing analysis (e.g., comparing risk disclosures across multiple years of a company's 10-K filings, or contrasting ESG disclosures across competitors). The ingestion service caches all page content — including images for the first 30 pages — in Redis with a 24-hour TTL, enabling instant retrieval without re-parsing.

**Section-Focused Chat.** The chat interface allows analysts to select an analysis focus (e.g., "ESG Analysis", "Key Risks") that injects the corresponding expert prompt as system context for the entire conversation. This grounds the LLaVA model in the specific analytical framework relevant to the analyst's current task, improving precision and reducing off-topic responses. Conversation history is maintained in the Streamlit session and included in each inference call to support multi-turn analysis. The interface is styled with a dark OLED design system (IBM Plex Sans, `#020617` background, `#22C55E` positive indicators) following investment management UI conventions.

**Concurrent Processing Architecture.** All computationally intensive operations run in dedicated thread pools: the ingestion service uses a `ThreadPoolExecutor(max_workers=10)` for document parsing; the extraction service uses a `ThreadPoolExecutor(max_workers=10)` for per-page OCR, table detection, and chart classification; and the report generator uses a `ThreadPoolExecutor(max_workers=4)` for parallel section generation. This architecture enables a 400-page SEC filing to complete extraction in approximately 40% of the time required by sequential processing on equivalent hardware.

---

## 4. FinDocBench Dataset

### 4.1 Collection Pipeline

FinDocBench was constructed from SEC EDGAR full-text submissions covering fiscal years 2018 through 2023. We selected 127 10-K annual reports from S&P 500 constituent companies, stratified by industry sector (GICS Level 1) to ensure diversity: 18 filings from Energy, 22 from Financials, 19 from Healthcare, 21 from Technology, 15 from Consumer Discretionary, 14 from Industrials, and 18 from other sectors. For each filing, we downloaded both the primary HTML/iXBRL document and any accompanying XBRL instance document from EDGAR. PDF renderings were obtained via the SEC's EDGAR full-submission viewer.

### 4.2 Question-Answer Annotation

QA pairs were created by a team of four annotators with backgrounds in financial analysis (CFA Level I qualified or equivalent). Each annotator was assigned a disjoint set of filings and asked to write questions that: (1) require evidence from two or more non-consecutive pages, (2) cannot be answered by reading any single page in isolation, and (3) require at least one non-text modality (table, chart, or XBRL fact) as part of the evidence chain.

After initial question writing, a second annotator reviewed each question to verify that the multi-page requirement was genuine and that a gold answer could be unambiguously derived from the filing. Inter-annotator agreement on answer correctness was measured at Cohen's kappa = 0.81, indicating strong agreement. The final dataset contains 412 QA pairs across the 127 filings, averaging 3.2 QA pairs per filing.

### 4.3 Dataset Statistics

| Statistic | Value |
|---|---|
| Total filings | 127 |
| Total QA pairs | 412 |
| Avg pages per filing | 84.3 |
| Avg supporting pages per QA | 3.7 |
| Max supporting pages | 11 |
| QA pairs requiring >= 3 pages | 61.4% |
| QA pairs with chart evidence | 38.1% |
| QA pairs with XBRL evidence | 44.7% |
| QA pairs with table evidence | 82.3% |
| Train / Dev / Test split | 280 / 66 / 66 |

*Table 1: FinDocBench dataset statistics.*

### 4.4 QA Type Distribution

| Reasoning Type | Count | Percentage |
|---|---|---|
| Numerical reasoning | 142 | 34.5% |
| Trend analysis | 98 | 23.8% |
| Cross-modal verification | 87 | 21.1% |
| Entity-anchored retrieval | 85 | 20.6% |
| **Total** | **412** | **100%** |

*Table 2: Distribution of reasoning types in FinDocBench.*

---

## 5. Experimental Setup

### 5.1 Hardware and Infrastructure

All experiments were conducted on a single server with 2x NVIDIA A100 80GB GPUs, 256GB DDR4 RAM, and 8TB NVMe SSD storage. The Neo4j graph database was deployed on the same machine with 64GB heap allocation. Total per-document ingestion and extraction time averaged 47 seconds for an 84-page filing. All reported latencies are end-to-end from question receipt to answer delivery.

### 5.2 Baseline Systems

We compare FinDocFlow against five baselines:

- **Single-page retrieval (BM25):** BM25 retrieval over individual pages, top-1 page fed to Llama 3.2.
- **Single-page retrieval (Dense):** Dense retrieval using `all-MiniLM-L6-v2` embeddings, top-1 page fed to Llama 3.2.
- **Long-context LLM only:** All pages concatenated (up to context window limit) and fed directly to Llama 3.2 without extraction or linking.
- **GPT-4 (no structure):** Full document text (no tables or charts) fed to GPT-4 Turbo via the OpenAI API.
- **FinMMDocR best system:** The best-reported configuration from [Li et al., 2024], reproduced using the authors' public code.

### 5.3 Evaluation Metrics

- **Accuracy:** Exact match or numerical equivalence (within 1% relative error for numerical answers). For free-text answers, BERTScore F1 threshold of 0.85.
- **Evidence Grounding Score (EGS):** Fraction of gold supporting pages appearing in the system's returned evidence set.
- **Mean Reciprocal Rank (MRR):** For the first gold supporting page, its reciprocal rank in the system's ranked evidence list.

### 5.4 Hyperparameters

Sentence-transformer encoding used `all-MiniLM-L6-v2`. CLIP used `ViT-L/14`. Entity resolution cosine similarity threshold: 0.82. Cross-reference traversal depth: 2. THINK→ACT→VERIFY max iterations: 3. Llama 3.2 generation: temperature 0.1, top-p 0.9, max 512 tokens per phase.

---

## 6. Results

### 6.1 Main Results

| System | Accuracy | EGS | MRR |
|---|---|---|---|
| Single-page BM25 | 38.2% | 0.31 | 0.29 |
| Single-page Dense | 41.5% | 0.38 | 0.35 |
| Long-context LLM only | 58.7% | 0.51 | 0.48 |
| GPT-4 (no structure) | 54.2% | 0.44 | 0.41 |
| FinMMDocR best [Li et al., 2024] | 62.4% | 0.55 | 0.53 |
| **FinDocFlow (ours)** | **71.3%** | **0.68** | **0.64** |

*Table 3: Main results on FinDocBench test set. Bold denotes best performance.*

FinDocFlow outperforms all baselines on all three metrics. The 8.9-percentage-point improvement over FinMMDocR is statistically significant (paired bootstrap, p < 0.01). GPT-4 (no structure) performs surprisingly poorly (54.2%), confirming that raw text inputs without structured table and chart extraction are insufficient for financial document reasoning.

### 6.2 Ablation Results

| Ablation | Accuracy | EGS | Delta Acc. |
|---|---|---|---|
| FinDocFlow (full) | 71.3% | 0.68 | — |
| — No entity linking (no graph) | 63.1% | 0.57 | -8.2 pp |
| — No chart parsing (text only) | 67.8% | 0.62 | -3.5 pp |
| — No hierarchy (flat context) | 65.4% | 0.59 | -5.9 pp |
| — No VERIFY step | 68.9% | 0.66 | -2.4 pp |
| — No cross-ref traversal | 66.2% | 0.61 | -5.1 pp |

*Table 4: Ablation results.*

The most impactful ablation is removal of entity linking (−8.2 pp), confirming that the Neo4j cross-page graph is the central contribution of FinDocFlow. The second most impactful ablation is removal of hierarchical context organization (−5.9 pp), followed by removal of cross-reference traversal (−5.1 pp).

### 6.3 Performance by Reasoning Type

| Reasoning Type | FinDocFlow | Long-context LLM | GPT-4 |
|---|---|---|---|
| Numerical reasoning | 68.3% | 54.9% | 50.7% |
| Trend analysis | 74.5% | 62.2% | 56.1% |
| Cross-modal verification | 73.6% | 55.2% | 48.3% |
| Entity-anchored retrieval | 69.4% | 61.8% | 61.2% |

*Table 5: Accuracy by reasoning type.*

FinDocFlow shows its largest improvements over baselines on cross-modal verification (+18.4 pp over long-context LLM) and trend analysis (+12.3 pp), the two question types most dependent on multi-page, multi-modal evidence integration.

---

## 7. Error Analysis

We manually analyzed all 19 incorrect answers from the test set and grouped them into three categories.

### 7.1 Chart Misinterpretation

Seven of 19 errors (36.8%) involved incorrect interpretation of chart content. The most common failure pattern was axis scale misreading: when a bar chart uses a logarithmic or broken y-axis, the CLIP encoding captures the visual appearance but does not encode the scale type, and the PaddleOCR axis-label extraction misidentifies the scale type.

### 7.2 Entity Disambiguation Failures

Six errors (31.6%) involved incorrect entity resolution, where the cross-page entity linker merged entities that should have remained distinct. The most common subcase involved parent company versus subsidiary reporting. Three of these errors occurred in financial sector filings, which have significantly more complex entity hierarchies.

### 7.3 Long-Range Numerical Reasoning

Six errors (31.6%) involved failures on questions requiring numerical reasoning across more than five pages. The failure pattern was typically cascading uncertainty within the THINK→ACT→VERIFY loop, where earlier extracted values were lost due to the limited 8K token context window of Llama 3.2.

---

## 8. Limitations

**English-only processing.** All components are calibrated for English-language documents. Extension to multilingual financial document understanding would require retraining the NER model and adopting a multilingual sentence encoder.

**US SEC filings only.** FinDocBench covers only SEC 10-K filings. The cross-reference detection regular expressions and XBRL concept normalization dictionary are specific to the SEC/US-GAAP framework.

**Ollama/Llama 3.2 latency.** The 3.2-second average latency is higher than GPT-4 Turbo (~1.8 seconds). Quantization (GGUF Q4_K_M) reduces latency to ~1.9 seconds with a ~1.5 pp accuracy penalty.

**No real-time streaming evaluation.** FinDocBench is a static benchmark evaluated in batch mode. Real-time evaluation with incremental graph updates has not been assessed.

---

## 9. Conclusion

We have presented FinDocFlow, an end-to-end pipeline for cross-page multimodal reasoning over heterogeneous financial documents, and FinDocBench, a new benchmark of 127 SEC 10-K filings with 412 expert-annotated multi-page QA pairs. FinDocFlow achieves 71.3% accuracy, outperforming the strongest prior system by 8.9 percentage points and long-context LLM baselines by 12.6 percentage points, while operating entirely on local hardware at zero API cost.

Future work will focus on: (1) extending FinDocBench to international filings; (2) integrating a specialized chart digitization model; (3) implementing scratchpad memory in the THINK→ACT→VERIFY loop; and (4) real-time streaming evaluation with incremental graph updates.

---

## References

Appalaraju, S., Jasani, B., Kota, B. U., Xie, Y., and Bhatt, R. (2021). DocFormer: End-to-end transformer for document understanding. *Proceedings of ICCV 2021*.

Araci, D. (2019). FinBERT: Financial sentiment analysis with pre-trained language models. *arXiv preprint arXiv:1908.10063*.

Chen, W., Zha, H., Chen, Z., Xiong, W., Wang, H., and Wang, W. Y. (2021). HybridQA: A dataset of multi-hop question answering over tabular and textual data. *Proceedings of EMNLP 2021 Findings*.

Feng, X., Liu, Y., and Zhao, D. (2023). UniDoc: A universal large multimodal model for simultaneous text detection, recognition, spotting and understanding. *arXiv preprint arXiv:2308.11592*.

Herzig, J., Nowak, P. K., Mueller, T., Piccinno, F., and Eisenschlos, J. (2020). TAPAS: Weakly supervised table parsing via pre-training. *Proceedings of ACL 2020*.

Huang, Y., Lv, T., Cui, L., Lu, Y., and Wei, F. (2022). LayoutLMv3: Pre-training for document AI with unified text and image masking. *Proceedings of ACM MM 2022*.

Kahou, S. E., Michalski, V., Atkinson, A., Kadar, A., Trischler, A., and Bengio, Y. (2018). FigureQA: An annotated figure dataset for visual reasoning. *Proceedings of ICLR 2018 Workshop*.

Li, J., Zhang, M., Chen, H., Liu, X., and Wang, Y. (2024). FinMMDocR: A benchmark for multimodal document reasoning in finance. *Proceedings of AAAI 2026*.

Ma, T., Li, Y., Zhao, Y., Liu, Z., and Shi, S. (2023). DORE: Document ordinal reasoning for multi-page legal document understanding. *Proceedings of EMNLP 2023*.

Masry, A., Long, D., Tan, J. Q., Joty, S., and Hoque, E. (2022). ChartQA: A benchmark for question answering about charts with visual and logical reasoning. *Proceedings of ACL 2022 Findings*.

Radford, A., Kim, J. W., Hallacy, C., Ramesh, A., Goh, G., Agarwal, S., Sastry, G., Askell, A., Mishkin, P., Clark, J., Krueger, G., and Sutskever, I. (2021). Learning transferable visual models from natural language supervision. *Proceedings of ICML 2021*.

Reimers, N. and Gurevych, I. (2019). Sentence-BERT: Sentence embeddings using Siamese BERT-networks. *Proceedings of EMNLP 2019*.

Smock, B., Pesala, R., and Abraham, R. (2022). PubTables-1M: Towards comprehensive table extraction from unstructured documents. *Proceedings of CVPR 2022*.

Xu, Y., Li, M., Cui, L., Huang, S., Wei, F., and Zhou, M. (2020). LayoutLM: Pre-training of text and layout for document image understanding. *Proceedings of KDD 2020*.

Yang, H., Liu, X. F., and Wong, D. F. (2020). FinBERT: A pretrained language model for financial communications. *arXiv preprint arXiv:2006.08097*.

Yang, S., Xu, Y., Cui, L., Wang, S., and Wei, F. (2022). TableFormer: Robust transformer modeling for table text encoding. *Proceedings of ACL 2022*.

Ye, Q., Xu, H., Hu, G., Ye, J., Yan, M., Danelljan, M., Li, C., Huang, F., and Qiu, X. (2023). mPLUG-Owl: Modularization empowers large language models with multimodality. *arXiv preprint arXiv:2304.14178*.

Zhao, Z., Ma, X., Hu, J., and Ye, D. (2022). MultiHiertt: Numerical reasoning over multi-hierarchical tabular and textual data. *Proceedings of ACL 2022*.

Zhao, Z., Liu, Z., Li, P., Tang, J., and Wen, J. (2023). MMRAG: Multimodal retrieval-augmented generation for document question answering. *arXiv preprint arXiv:2311.09777*.

Zhou, P., Chen, L., Zhang, Y., and Qian, T. (2024). LongDocRAG: Hierarchical chunking for long-document retrieval-augmented generation. *Proceedings of NAACL 2024*.

Zhu, F., Lei, W., Huang, Y., Wang, C., Zhang, S., Lv, J., Feng, F., and Chua, T.-S. (2021). TAT-QA: A question answering benchmark on a hybrid of tabular and textual content in finance. *Proceedings of ACL 2021*.
