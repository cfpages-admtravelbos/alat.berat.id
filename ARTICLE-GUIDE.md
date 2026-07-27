<!-- BEGIN MANAGED ARTICLE GUIDE -->
# Article Guide — alat.berat.id

Status: repository-local instruction for expanding one prebuilt article outline at a time
Public route contract: `/artikel/[slug].html`
Source route evidence: sitemap XML, 3794 routes discovered during packet generation
Reader community name: `Berat.id`

## Exact prompt to give the lower-capability model

```text
Read AGENTS.md and ARTICLE-GUIDE.md completely. Expand only artikel/[EXACT-SLUG].md in place. Follow every scope, evidence, internal-link, and section instruction already inside that file. Do not edit any other file. Do not publish, hydrate HTML, update a sitemap, or push Git.
```

Replace `[EXACT-SLUG]` with one existing filename. Assign one article per run.

## Required reading order

1. `AGENTS.md`
2. this `ARTICLE-GUIDE.md`
3. exactly one assigned `artikel/[slug].md`

Do not load the portfolio ledger, OneDrive memory, another repository, the full catalog, or the full research file. The assigned outline already contains the needed local context.

## What the model must do

1. Confirm the assigned file's `article_id`, `title`, `slug`, primary intent, scope boundary, and final route.
2. Preserve front matter exactly except:
   - change `status: outline` to `status: draft` after the article is fully expanded;
   - keep `writing_contract_version: "native-id-v2"` to distinguish this native-Indonesian contract from the legacy revision backlog;
   - rewrite an inherited English `description` as a concise, natural Indonesian reader summary without changing the article's intent;
   - set `date_modified` only when the user supplies or authorizes a real modification date;
   - prune `sources:` to the exact original URLs actually cited in rendered prose; do not keep unused candidate sources or add new research.
   Every other field is immutable. Never change `article_id`, `title`, `slug`, `publication_date`, `publication_date_basis`, `date_modified`, `parent_topic`, `primary_intent`, `reader_community`, `reader_address`, `final_route`, or `technical_review`.
3. Replace instructional bullets under the detailed outline with finished Indonesian prose.
4. Answer the title's main question in the opening two or three paragraphs.
5. Keep every H2 focused on the distinct reader question stated beneath it.
6. Use original sources embedded in the evidence packet. Put the source link near the supported consequential claim. Use only the packet's stated safe fact/purpose/limit for that source; a URL, law number, or ISO record does not authorize guessing its subject or requirements.
7. Add internal links only where they help the reader take a next step. Use the exact routes already listed in the file.
8. Preserve every limitation, professional-review condition, and stop-work boundary.
9. Finish with a concrete next action or operating rule, not a generic summary.
10. Run the completion checklist inside the file, then delete that production-only heading and all of its checkboxes from the finished public article.
11. Copy the real validator result into the worker receipt. Never claim `errors=0` unless the displayed command actually returned it.

## Required validation

After drafting, run:

```powershell
python "$env:OneDrive\MD\skills\write-portfolio-articles\scripts\validate_article_draft.py" "artikel\[slug].md" --repo .
```

Replace `[slug]` with the assigned filename. If `$env:OneDrive` is unavailable, ask the coordinator for the canonical validator path; do not silently skip validation.

## Writing style

- Write as if the thought began in Indonesian, not as an English technical sentence translated word by word.
- Reader understanding takes precedence over displaying technical vocabulary. State the plain idea first, define every necessary trade/English term immediately, then explain what it changes for the reader.
- Never leave an acronym or imported term unexplained on first use. Put the Indonesian meaning first and the accepted abbreviation in parentheses when it remains useful.
- Remove accidental Chinese/Japanese/Korean or other unrelated-script residue. Do not copy an unfamiliar glyph merely because it appeared in generated text.
- Treat English planning labels inherited from the outline as internal wording, not approved public prose. Translate bare `scope`, `hold point`, `handover`, `baseline`, `shortcut`, `cutout`, `red flag`, `brief`, `review`, `finishing`, `artwork`, `approved drawing`, and `release`; keep a trade term only after its Indonesian meaning is clear.
- Do not force an uncommon Indonesian translation for a term that Indonesians naturally use in English or as a loanword. Keep familiar terms such as `stainless steel`; explain them only when the intended reader may not understand them.
- Keep titles and headings Indonesian-first. Put useful imported component labels such as `face`, `return`, `backing`, or `mounting` in a first-use body explanation.
- Keep standardized `[NEEDS ...]` labels where evidence is unresolved, but write the explanation after the colon in natural Indonesian.
- Sound like Syamsul as a friendly, candid operator-teacher throughout the article: direct answer first, mechanism next, evidence and decisions after that.
- Prefer natural verbs such as `periksa`, `cocokkan`, `catat`, `tahan`, or `minta bukti` over noun-heavy translated constructions.
- Use short, natural transitions and at least one concrete example or realistic reader question where it reduces abstraction.
- Light pivots such as `nah`, `jadi`, `singkatnya`, `sederhananya`, `begini`, or `biar tidak salah langkah` are welcome when they fit. Do not force slang, jokes, or invented experience.
- Address the reader warmly as `Sobat Berat.id`, `Kawan Berat.id`, or `Teman Berat.id`. Use the exact opening salutation assigned inside the article file.
- Sprinkle these community addresses naturally three to five times in a typical long article, including the opening. Good positions are a consequential warning, a decision checkpoint, a practical example, and the conclusion. Do not force one into every section or repeat the same phrase in adjacent paragraphs.
- Use `Anda` naturally between those community-address moments. Use `saya` only when the outline contains real Syamsul-supplied experience.
- Vary sentence length. Prefer concrete actors, objects, actions, and consequences.
- Explain an English trade term on first use when Indonesian readers may not know it.
- Read the visible prose aloud; rewrite anything grammatical but unnatural in Indonesian conversation.
- Use a checklist, table, decision tree, warning, or scenario only when it reduces reader effort.
- Giving the direct answer early is an opening strategy, not permission to rush the rest. After the short answer, slow down and patiently unpack the idea for an Indonesian reader who is intelligent but has never managed this equipment or process.
- For every substantive H2 except the conclusion, make the explanation chain understandable: start from a familiar situation or reader question, explain the plain meaning, show how or why it happens, state the practical consequence, then give an example, check, or decision. Vary the prose naturally; do not expose this as a repeated formula.
- Do not use a list of terms, risks, or steps as a substitute for teaching. Explain why the highest-consequence items matter and what the reader would notice, ask, check, or do differently.
- Do not stack several unfamiliar technical terms in one sentence and move on. If two or more imported terms are necessary, break the explanation apart and define each at first use. Familiar Indonesian trade terms may remain, but the surrounding idea must still be clear to a non-specialist.
- Before finishing, run a lay-reader pass: ask “Apa maksudnya?”, “Mengapa ini terjadi?”, “Contohnya seperti apa?”, and “Jadi pembaca harus berbuat apa?” for each main section. If the visible prose does not answer those questions, elaborate it before validation.
- Most technical articles need about 1,600–2,400 useful words to teach the subject patiently. A complete 1,000–1,599-word article may be accepted with a soft warning; below 1,000 is a hard failure. Never reach a range through repetition, generic context, or padding.

## Evidence rules

- `GLOBAL_RESEARCH.md` was used to prepare the packet, but it is not a public source. Cite the original URLs embedded in the assigned article.
- A standards catalogue page proves identity/status/public scope only, not hidden clauses.
- A method does not prove a real product or project passed.
- A material property does not automatically prove installed-system performance.
- Foreign guidance is not Indonesian law.
- Project prices, capacity, availability, test results, warranties, measurements, and case outcomes require current project evidence.
- Keep `[NEEDS ...]` when the missing fact is consequential. Do not disguise uncertainty with confident wording.

## Internal-link rules

- Existing local routes in the assigned file are candidates; use only those that genuinely answer the next reader question.
- Planned sibling article routes are marked future. Do not link them as live until their source file is reviewed and the HTML route exists.
- Use descriptive natural anchors, not repeated exact-match keywords.
- Do not invent a route or add unrelated “Baca juga” links.
- Helpful density is welcome; link stuffing is not.

## Publication-date rule

The front matter's `publication_date` is the appointed historical CMS date. Preserve it exactly. Keep `publication_date_basis: editorial_backfill`. This is an intentional WordPress/CMS-style editorial workflow. Do not convert it to a future date.

## Never do

- Do not change the slug, article ID, parent topic, intent, or boundary.
- Do not change the assigned title, historical publication date, `date_modified`, reader community/address, final route, or technical-review state.
- Do not copy metadata, prose, IDs, dates, or conclusions from another article.
- Do not infer a source's meaning from its identifier. For example, never describe a law as construction licensing unless the packet explicitly supports that statement.
- Do not expose `BEGIN MANAGED IMAGE PLAN`, `Image plan`, `Exact Markdown to insert`, or other production instructions as public prose. Keep the whole plan in one multiline HTML comment and place its exact Markdown image outside the comment.
- Do not repeat a paragraph or paste the conclusion twice.
- Do not create or execute Python, PowerShell, JavaScript, shell scripts, macros, loops, templates, or bulk-generation commands for article production. The official validator command is the sole allowed Python execution during external writing.
- Do not claim Syamsul personally performed a project unless the file supplies that evidence.
- Do not invent quotes, statistics, prices, standards clauses, measurements, clients, or case studies.
- Do not copy an existing landing page or another article.
- Do not write generic openings such as “Di era digital” or “Seiring perkembangan zaman.”
- Do not mention SEO, keywords, AI, prompts, outlines, or evidence gates in public-facing prose.
- Do not edit more than the one assigned file.

## Definition of a completed draft

- The opening gives a direct answer.
- Every required section is expanded and non-repetitive.
- A reader outside the trade can understand every main section without decoding a compressed list of jargon.
- Every substantive section explains meaning, mechanism, consequence, and a concrete example/check/decision where useful; it does not merely name them.
- Consequential claims have original sources or visible review markers.
- Every cited source stays within the safe fact/purpose/limit stated in the packet; no law or standard has been assigned a guessed subject.
- Internal links are relevant and use exact local routes.
- No instruction bullets remain in the public article body.
- Front matter remains valid and `status` is `draft`.
- All immutable front-matter values still match the assigned outline exactly, and `date_modified` remains unchanged.
- No unrelated foreign-script residue, duplicated paragraph, or public production scaffold remains.
- The draft ends with an actionable conclusion and honest boundary.

No HTML hydration, deployment, sitemap generation, or GSC submission is authorized by this guide.
<!-- END MANAGED ARTICLE GUIDE -->

<!-- BEGIN MANAGED ARTICLE IMAGE GUIDE -->
## Image instructions for every article

The assigned outline contains one managed `Image plan` copied from `IMAGE_CATALOG.md`. Follow that block exactly; do not open the full catalog during a one-article writing run.

1. Place the primary image after the opening has already given the short answer, unless the plan names another section.
2. Convert the plan's `Exact Markdown to insert` code into a real Markdown image line in the public article body. Do not leave the URL only inside the internal instruction block.
3. Use the exact URL and supplied alt-text brief. Make alt text concise and functional; do not add details that are not stated by the filename/source metadata.
4. Put the supplied caption or credit immediately below the real image. Preserve the creator, source-page link, and license link for every external image.
5. A local repository URL is preferred because it avoids a third-party delivery dependency. An external hotlink is allowed only when its complete provenance is embedded in the plan.
6. Do not use an image as evidence for a technical, commercial, safety, compliance, performance, or project claim.
7. Do not add decorative duplicate images. One strongly relevant image is better than several weak or repetitive images.
8. Do not rename, download, optimize, or edit an image in the writing stage. Image processing and HTML hydration are separate later stages.

The catalog was prepared without visual inspection to keep the rollout lean. Treat its filename/metadata inference as a subject label only, never as permission to narrate unseen details.
<!-- END MANAGED ARTICLE IMAGE GUIDE -->
