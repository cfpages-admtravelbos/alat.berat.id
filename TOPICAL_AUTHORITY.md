# Topical Authority — alat.berat.id

## Role and boundary

`alat.berat.id` is the Indonesian heavy-equipment knowledge and commercial-support property for people who must understand, select, procure, mobilize, operate, maintain, and retire construction, earthmoving, lifting, roadwork, concrete, hauling, quarry, and mining equipment. Its primary readers are project owners, contractors, procurement teams, site engineers, fleet managers, supervisors, operators, mechanics, and buyers comparing rental or purchase.

The knowledge layer must explain decisions and risks without pretending to be an engineering approval, operator certification, lift plan, transport permit, environmental approval, OEM manual, or site-specific quotation. Existing product, service, and location routes retain transactional intent. Planned articles own non-geographic educational intent. A city or route page is publishable only when it contains verified local logistics, regulation, terrain, supply, or case evidence; changing a place name is not editorial coverage.

## Evidence audited

- Canonical source audited: `cfpages-admtravelbos/alat.berat.id`, branch `main`, static WordPress export.
- `sitemap-complete.xml` declares 3,794 exact URLs. All are exact-string unique, but only 2,157 remain after normalizing a trailing slash.
- The sitemap therefore contains 1,637 slash/no-slash duplicate groups.
- Dominant patterns: 3,284 `/jual-rental/<machine>-<place>` entries, 133 `/jual-sewa-alat-berat-<place>` entries, and 225 `/towing/rute/<origin>-<destination>` entries.
- Fourteen product-location families each expose about 129–131 normalized destinations: asphalt finisher, asphalt mixing plant, bulldozer, compactor/roller, concrete mixer, concrete pump truck, dredger, dump truck, excavator, motor grader, stone crusher, tower crane, prime mover, and wheel/track loader.
- There are 63 raw `/jasa/` or `/layanan/` sitemap entries, four archive-like entries, 29 raw truck entries, nine excavator entries, and a smaller set of machine/category hubs.
- One malformed sitemap URL retains the unresolved `%jual-rental_slug%` placeholder.
- Sampled pages show real commercial and introductory coverage for excavators and variants, asphalt and concrete equipment, land clearing, mining services, heavy-equipment transport, truck crane capacities, maintenance, equipment management, and component rebuild.
- Many clean-directory `index.html` files redirect to sibling `.html` pages while both slash and non-slash URL forms appear in the sitemap.
- No repository-local `AGENTS.md` or prior topical-authority files existed at audit time.

Counts describe repository and sitemap evidence, not indexation, traffic, availability, certification, project experience, or regulatory compliance.

## Existing coverage and risks

| Existing URL/pattern | Observed role/problem | Decision | Destination/owner | Verification needed |
|---|---|---|---|---|
| `/` | Commercial overview mixes machine taxonomy, service claims, and fleet-management messaging | keep | Homepage remains commercial; `panduan-alat-berat-untuk-proyek` owns the knowledge entry point | Verify current offers, company identity, substantiation for trust claims, and homepage canonical |
| `/jenis`, `/klasifikasi` and slash variants | Broad taxonomy intent with `.html` content and clean-directory redirects | merge | One maintained classification hub; redirect the weaker duplicate form | Compare backlinks, GSC queries, canonical tags, and redirect behavior before choosing the surviving URL |
| Core machine routes such as `/excavator/`, `/bulldozer`, `/tower-crane` | Product or category pages also contain introductory education | expand | Keep transactional/category intent; link to dedicated knowledge articles by task | Confirm which URL variant is canonical and separate quote CTAs from neutral guidance |
| Variant routes such as `/excavator/backhoe` and `/concrete/pump-truck` | Useful entity pages, but slash and non-slash forms coexist | canonicalize | One canonical URL per machine or variant | Crawl response codes, canonicals, internal links, sitemap output, and historical signals |
| `/jual-rental/<machine>-<place>` | 3,284 sitemap entries form a large machine-by-location matrix; local differentiation is not established by route evidence | manual review | Keep only pages with verified local inventory, logistics, service area, or project evidence; consolidate the rest into product and coverage hubs | Sample content similarity, availability truth, local proof, leads, indexation, and GSC impressions before any redirect/noindex decision |
| `/jual-sewa-alat-berat-<place>` | 133 generic location pages may overlap every machine-location page in the same place | manual review | A genuinely useful regional fleet page may own broad local intent; machine pages must own a distinct available-machine intent | Test same-query overlap, content uniqueness, lead value, and whether a real service boundary exists |
| `/towing/rute/<origin>-<destination>` | 225 raw route URLs, commonly duplicated by trailing slash, risk route-swapped content and overlap with heavy-equipment transport | manual review | `perencanaan-rute-mobilisasi-alat-berat` owns general education; retain route pages only with verified route constraints and service evidence | Validate route data, dimensional restrictions, ferry/port dependencies, permit currency, and commercial coverage |
| `/jasa/pengiriman-alat-berat` | Commercial transport page includes general tips and cross-service language | expand | Route remains service intent; ABR-07 and ABR-14 knowledge assets own neutral planning | Verify provider scope, cargo insurance language, permits, equipment, and claims |
| `/jasa/pertambangan`, `/jasa/pembersihan-lahan`, other `/jasa/` routes | Service pages contain broad educational sections and may promise disciplines beyond evidence | manual review | Keep proven service scope; link to machine/application knowledge; remove unsupported practice claims | Confirm licenses, competent personnel, portfolio evidence, and actual deliverables |
| `/layanan/maintenance-service`, `/layanan/component-rebuild`, `/layanan/equipment-management-solutions` | Useful lifecycle services, but service claims need operational proof | expand | Commercial routes own offers; ABR-15, ABR-16, and ABR-18 own educational intent | Verify workshop capability, OEM boundaries, parts traceability, warranty, and service records |
| `/truk/*` | Several truck types appear in both `.html` and clean-directory forms and extend beyond heavy equipment | merge | Retain truck pages that support equipment hauling, site material flow, lifting, or concrete operations; separate unrelated freight intent | Check query demand, conversion role, and overlap with logistics/client properties |
| `/author/*`, `/berita/`, `/uncategorized/` | Archive-like URLs add little standalone task value | noindex | Articles and maintained hubs own discoverable intent | Confirm archive traffic/backlinks and ensure crawlable article discovery remains |
| `%jual-rental_slug%/compactor-roller-tasikmalaya` | Unresolved permalink placeholder in sitemap | remove | Correct source route and regenerate sitemap | Confirm response status, internal links, GSC indexation, and intended destination |
| `sitemap-complete.xml` | 3,794 entries include 1,637 trailing-slash duplicate groups | canonicalize | Sitemap must list only final canonical 200-status URLs | Crawl all sitemap URLs, verify canonical/redirect consistency, regenerate, and resubmit |

## Coverage matrix

| Completeness lens | Topic owners | Coverage decision |
|---|---|---|
| Definition, vocabulary, history, taxonomy | ABR-01 | One stable knowledge system distinguishes machine family, function, configuration, attachment, capacity, and Indonesian/English terms |
| Anatomy, materials, mechanisms, measurement | ABR-08, ABR-09, ABR-10, ABR-12 | Component and calculation claims require diagrams, OEM data, units, assumptions, and reviewer gates |
| Need recognition, survey, requirements, comparison | ABR-02, ABR-03, ABR-04, ABR-05, ABR-06 | Selection starts from work, material, cycle, site, and risk—not brand or nominal capacity alone |
| Budget and procurement | ABR-13 | Rental, purchase, tender, contract, inspection, and total-cost intents have separate owners |
| Preparation, mobilization, installation | ABR-07, ABR-12, ABR-14 | Route, ground, access, assembly, exclusion-zone, and permit checks precede arrival or lifting |
| Commissioning, operation, handover | ABR-11, ABR-12, ABR-18 | Competent personnel, pre-start checks, load control, records, and acceptance evidence are mandatory |
| Inspection and maintenance | ABR-10, ABR-15 | System explanations support interval-based inspection without replacing OEM schedules |
| Troubleshooting, repair, rebuild | ABR-16 | Symptom isolation has stop conditions; intrusive diagnosis and rebuild require qualified technicians |
| Upgrade, replacement, decommissioning | ABR-15, ABR-16, ABR-17 | Repair-versus-replace, residual value, reuse, waste, and end-of-life are explicit |
| Stakeholder and site context | ABR-02, ABR-11, ABR-13, ABR-18 | Owners, engineers, procurement, supervisors, operators, mechanics, and neighbors get distinct decisions |
| Climate, geography, retrofit, scale | ABR-02, ABR-07, ABR-12, ABR-17 | Rain, heat, coast, weak ground, constrained sites, occupied projects, and remote logistics alter substance; they do not justify place-name swapping |
| Safety, health, failure modes | ABR-11, ABR-12, ABR-15, ABR-16 | Safety-critical content requires competent review, stop-work cues, manufacturer limits, and incident-prevention framing |
| Standards and regulation | ABR-11, ABR-12, ABR-14, ABR-17, ABR-18 | Cite current primary Indonesian regulator/standards sources at publication; do not reproduce unverifiable clause numbers |
| Environmental impact | ABR-06, ABR-07, ABR-17 | Fuel, emissions, spill, noise, dust, sediment, waste, route, and rehabilitation impacts are planned |
| Fundamentals, how-to, comparison, diagnosis | ABR-01 through ABR-18 | Each format owns a distinct task; unsafe hands-on work is not framed as DIY |
| Calculators and visual reference | ABR-02, ABR-07, ABR-09, ABR-12, ABR-13, ABR-15 | Tools expose inputs, units, uncertainty, exclusions, and professional-review thresholds |
| Case studies | ABR-02, ABR-07, ABR-12, ABR-16, ABR-17 | Publish only from documented real projects with permission; no invented outcomes |
| Commercial support | ABR-13, ABR-14, ABR-18 | Educational articles may support procurement but do not absorb service-page quote intent |
| News and trends | ABR-10, ABR-17, ABR-18 | Cover durable changes such as telematics, electrification, and governance only when maintainable and sourced |

## Topical map

| Topic ID | Parent topic | Reader outcome | Required subtopics/questions | Evidence/formats | Boundary | Article target |
|---|---|---|---|---|---|---:|
| ABR-01 | Foundations, terminology, and classification | Readers can identify a machine by function and describe requirements without confusing brand, family, attachment, or capacity | Heavy-equipment definition; Indonesian and English terms; function-based classes; mobile versus fixed plant; wheeled versus tracked; production versus support equipment; naming traps; evolution of mechanization | Taxonomy diagram; glossary; historical sources; annotated machine silhouettes; expert review | Does not recommend a machine for a site; ABR-02 owns selection and existing product routes own availability | 6 |
| ABR-02 | Site survey, sizing, and equipment selection | Project teams can translate work volume, material, access, ground, cycle, climate, and schedule into a defensible shortlist | Task and material properties; production target; cycle time; reach and dump height; ground pressure; access envelope; slope; visibility; weather; redundancy; selection matrix; when mechanization is unnecessary | Survey checklist; decision tree; calculation worksheet; site plan; OEM data; engineer review | Does not teach operation or quote a fleet; ABR-11 owns operation and ABR-13 owns procurement | 6 |
| ABR-03 | Earthmoving, excavation, loading, and grading | Readers can distinguish excavator, backhoe, bulldozer, loader, scraper, and grader roles across the earthwork cycle | Digging versus pushing versus loading versus grading; soil and rock behavior; trench, basement, cut-fill, stockpile, land clearing; reach; breakout; haul interface; productivity bottlenecks; machine combinations | Process diagram; machine comparison; production model; geotechnical input; field photos | Does not cover quarry processing or lifting; ABR-06 owns quarry/mining and ABR-04 owns lifting | 6 |
| ABR-04 | Cranes, lifting, and material handling | Readers can recognize lifting systems and know which data must enter a competent lift decision | Tower, mobile, crawler, truck-mounted, telehandler and forklift distinctions; load chart concepts; radius; boom configuration; rigging interface; tandem lifts; visibility; wind; assembly; exclusion zones | Anatomy diagrams; load-chart reading exercise; lift-plan checklist; manufacturer manuals; lifting specialist review | Does not approve a lift or publish a universal capacity; ABR-12 owns stability calculations and commercial crane routes own quotations | 6 |
| ABR-05 | Roadwork, asphalt, and compaction equipment | Road teams can connect each machine to production stage and quality control | Asphalt plant; paver; grader; roller types; soil versus asphalt compaction; lift thickness; moisture and temperature concepts; rolling pattern; paving train; segregation; density evidence; small-site alternatives | Process map; decision table; quality checklist; PUPR/BSN and manufacturer sources; field measurements | Does not specify a pavement design or sell roadwork; `jalan.co.id` may independently own pavement-system depth and service routes own offers | 6 |
| ABR-06 | Concrete, quarry, mining, dredging, and processing plant | Readers can select the correct equipment-system family for material production, placement, extraction, and processing | Mixer versus batching; concrete pump; crusher and screening train; conveyors and feeders; dewatering; dredger types; mining fleet interaction; material gradation; dust, sediment and guarding; fixed versus mobile plant | System schematics; process-flow diagrams; material tests; manufacturer data; ESDM/PUPR/KLHK source gates | Does not design concrete mixes, mines, quarries, or dredging permits; specialist properties and licensed professionals own those decisions | 6 |
| ABR-07 | Hauling, logistics, and route planning | Logistics teams can match cargo, carrier, securement, route, and handoff without relying on a city-swapped page | Dump and articulated trucks; prime mover and lowbed; towing boundaries; dimensions and mass; axle/load distribution concepts; loading and lashing; bridge/clearance survey; port/ferry handoffs; weather; emergency plan; documentation | Route-survey template; carrier comparison; load-distribution worksheet; securement diagram; Kemenhub and carrier evidence | Does not quote a route or certify legal movement; `/jasa/pengiriman-alat-berat` owns service intent and ABR-14 owns permit workflow | 6 |
| ABR-08 | Machine anatomy, structures, undercarriage, tires, and wear | Owners can identify major assemblies and connect wear patterns to duty and environment | Frame; boom/stick; bucket; counterweight; cab; undercarriage; tracks; tires; pins/bushings; bearings; ropes; structural welds; corrosion; wear limits; visual warning signs | Exploded diagrams; wear atlas; inspection photos; OEM limits; NDT specialist review | Does not prescribe repairs or generic discard limits; ABR-15 owns inspection programs and ABR-16 owns diagnosis/rebuild | 6 |
| ABR-09 | Attachments, work tools, and compatibility | Buyers can specify an attachment by task and verify interface, hydraulic, structural, and control compatibility | Buckets; breakers; augers; grapples; rippers; compactors; quick couplers; forks; lifting points; carrier class; flow/pressure; coupler standards; guarding; balance; tool wear; change procedure | Compatibility worksheet; interface diagram; OEM cross-check; risk checklist; competent-person review | Does not declare an attachment safe from model name alone; ABR-12 owns stability effects and product routes own stock | 6 |
| ABR-10 | Engines, hydraulics, electrical systems, controls, and telematics | Operators and owners can understand system behavior, data, and early warning signals | Diesel and aftertreatment concepts; cooling; filtration; hydraulic pumps/valves/cylinders; contamination; batteries and charging; sensors; control modes; telematics; fault codes; data ownership; cybersecurity; energy recovery | System diagrams; fluid path; trend charts; OEM manuals; data-governance checklist | Does not bypass emissions or safety systems and does not replace OEM diagnostics; ABR-16 owns fault isolation | 6 |
| ABR-11 | Safe operation and jobsite K3 | Supervisors can build a control system around people, machines, traffic, energy, visibility, and changing conditions | Hazard identification; competent operator; pre-start; seat/restraint; blind spots; spotters; traffic plan; exclusion zones; slope and edge hazards; overhead/underground utilities; lockout; weather; fatigue; emergency response | JSA template; traffic-plan diagram; toolbox checklist; Kemnaker and OEM primary sources; K3 expert review | Does not certify an operator or replace site procedures; ABR-12 owns engineered stability and ABR-18 owns competency governance | 6 |
| ABR-12 | Loads, stability, ground bearing, slopes, and engineered limits | Engineers and supervisors can recognize critical variables and know when calculation and approval are mandatory | Center of gravity; rated versus working load concepts; load charts; dynamic effects; radius; ground bearing pressure; mats; bearing capacity; slope; edge distance; outrigger reactions; wind; temporary works; uncertainty and safety factors | Worked examples with synthetic data; unit-checked calculator; ground sketch; primary standards; geotechnical/structural/lifting review | Does not output a site approval, safe capacity, or lift plan; actual work requires verified machine data and competent engineering | 6 |
| ABR-13 | Rental, purchase, tendering, contracts, and total cost | Procurement teams can compare commercial options on scope, risk, utilization, condition, service, and lifecycle cost | Rent versus buy; wet versus dry hire; utilization; rates and exclusions; mobilization; fuel; operator; overtime; standby; inspection; warranty; parts; insurance; bid normalization; contract clauses; residual value | TCO model; bid-comparison sheet; inspection checklist; contract issue list; accountant/legal review | Does not publish universal prices, availability, tax, or legal advice; commercial routes own current quotations | 6 |
| ABR-14 | Mobilization, assembly, permits, and site readiness | Project teams can prepare access, permits, assembly space, utilities, and acceptance before equipment starts work | Dimensional survey; transport configuration; road and bridge constraints; permits; escorts; port/ferry; unloading; assembly; crane erection; temporary works; utilities; public protection; delivery inspection; demobilization | Readiness checklist; responsibility matrix; route plan; Kemenhub/local-authority source gate; OEM assembly manual | Does not claim a permit is unnecessary or approve a route; ABR-07 owns carrier selection and ABR-12 owns engineered support | 6 |
| ABR-15 | Inspection, preventive maintenance, fluids, and wear management | Fleet teams can build condition-based routines without substituting generic intervals for OEM requirements | Pre-start; daily/periodic inspection; lubrication; fluids and sampling; filters; cooling; undercarriage; tires; ropes; structural inspection; service records; contamination control; storage; seasonal/remote-site adjustments | Layered checklists; fluid trend; wear chart; CMMS fields; OEM schedules; technician review | Does not prescribe a universal interval or authorize continued use after a critical defect; ABR-16 owns diagnosis and rebuild | 6 |
| ABR-16 | Troubleshooting, repair, component rebuild, and replacement | Teams can triage symptoms, stop unsafe operation, collect evidence, and choose repair, rebuild, or replacement | Overheating; low power; hydraulic drift; contamination; abnormal noise/vibration; electrical faults; cracks; repeated failures; fault trees; isolation; root-cause analysis; rebuild scope; quality evidence; warranty; economic threshold | Symptom decision trees; sample-data case format; teardown evidence checklist; OEM tolerances; qualified technician review | Does not provide unsafe bypasses, intrusive DIY repair, or invented case results; `/layanan/component-rebuild` owns commercial service | 6 |
| ABR-17 | Fuel, emissions, noise, spills, waste, and environmental performance | Owners can reduce environmental harm and compare interventions using measurable boundaries | Idle and fuel use; emissions systems; electrification/hybrid limits; noise/vibration; dust; spill prevention and response; used oil/filters/batteries; wash water; sediment; biodiversity; rehabilitation; lifecycle and decommissioning | Baseline worksheet; spill map; waste-flow diagram; KLHK/ESDM/OEM sources; environmental specialist review | Does not certify compliance or claim zero emissions; project approvals and licensed waste handling remain external | 6 |
| ABR-18 | Operators, fleet governance, productivity, and evidence | Organizations can define roles, competence, records, KPIs, and data controls that improve reliable production without rewarding unsafe behavior | Competency matrix; induction; supervision; shift handover; fatigue; dispatch; utilization; availability; productivity; downtime codes; telematics governance; privacy; incident learning; contractor controls; continuous improvement | RACI; competency matrix; KPI dictionary; dashboard wireframe; Kemnaker/OEM sources; operations review | Does not issue certification or promise productivity gains; ABR-11 owns task controls and ABR-13 owns commercial utilization decisions | 6 |

## Related-domain opportunities

- `kapal.berat.id` may independently explain marine heavy equipment, barges, dredging support, deck loading, ports, and sea transport from a vessel-first viewpoint. Overlap across domains is allowed.
- `jalan.co.id` can cover pavement design, road defects, and finished-road performance while `alat.berat.id` explains the machines and production controls.
- `safety.co.id` can publish broader K3-system and training perspectives; `alat.berat.id` still needs equipment-specific hazards, controls, and evidence.
- `genset.co.id`, `beton` properties, mining properties, and logistics properties may independently deepen their systems. Contextual links are useful only when the destination genuinely advances the reader's task.
- No topic is removed merely because another Syamsul-owned domain covers it. Cannibalization controls in this plan apply only within `alat.berat.id`.

## Consolidation plan

1. Export a crawl with response code, final URL, canonical, title, H1, word count, internal links, and content hash for all 3,794 sitemap URLs.
2. Select one slash convention and one public form for `.html`/clean-directory pairs using live behavior, backlinks, and GSC evidence. Redirect every alternate form and regenerate the sitemap.
3. Remove the unresolved `%jual-rental_slug%` URL from generation after confirming its intended destination.
4. Cluster the 3,284 product-location, 133 general-location, and 225 route URLs by normalized intent and content similarity. Do not bulk-delete based on route names alone.
5. Keep a geographic page only when it proves local availability or provides substantive local logistics, access, regulatory, terrain, weather, or case information. Merge or noindex weak pages after measuring traffic, links, and leads.
6. Separate service offers from educational explanations. Preserve useful existing URLs where their history and intent align; link them to the new knowledge hubs instead of replacing them for cosmetic reasons.
7. Noindex low-value archives after confirming articles remain crawlable through hubs and XML sitemaps.

## Internal-link architecture

- `panduan-alat-berat-untuk-proyek` is the editorial entry hub. It links to all 18 parent-topic hubs and existing machine/service routes by reader task.
- ABR-01 definitions link forward to ABR-02 selection. Selection pages link laterally to the relevant application cluster: ABR-03, ABR-04, ABR-05, or ABR-06.
- Machine and attachment pages link to ABR-08 anatomy, ABR-09 compatibility, ABR-10 systems, ABR-12 limits, and ABR-15 maintenance only where the exact component or decision is relevant.
- Diagnostics in ABR-16 link backward to ABR-15 prevention and forward to repair/rebuild/replacement decisions. Critical symptoms also link to ABR-11 stop-work controls.
- Logistics pages link in sequence: ABR-07 carrier/route selection → ABR-14 permits/readiness → ABR-12 ground/support limits → ABR-11 site traffic and exclusion zones.
- Procurement pages in ABR-13 may link to commercial product/service routes only after readers have enough scope, condition, and risk information to request a meaningful quotation.
- Every article links to its parent hub; every hub links to every child. Related links are assigned by task and lifecycle rather than copied as a generic block.

## Evidence and editorial standards

1. Separate observed repository evidence, sourced fact, calculation, practitioner judgment, and editorial hypothesis.
2. For K3 and operation, use current primary material from Kemnaker, relevant Indonesian regulators/standards bodies, OEM operation/maintenance manuals, and competent K3 practitioners. Every procedure states prerequisites, PPE/control assumptions, stop conditions, and who may perform it.
3. For lifting, stability, ground bearing, and temporary support, show inputs, units, configuration, uncertainty, and review threshold. Never infer capacity from marketing names. A competent engineer/lifting specialist must review publication and all real-work decisions.
4. For transport, verify dimensions, mass, axle/load distribution, carrier rating, securement, route clearance, bridge/port/ferry constraints, and current Kemenhub/local-authority requirements. An article cannot grant a permit or certify a route.
5. For mining, quarry, dredging, and environmental topics, gate claims through current ESDM, KLHK, PUPR, BSN, permit, and manufacturer evidence as applicable. Do not quote clause numbers unless checked on the publication date.
6. Use synthetic, clearly labeled numbers for worked examples until real project inputs are available. Never invent tests, incidents, prices, inventory, case studies, certifications, or performance gains.
7. Tables comparing machines use the same work definition and disclose configuration differences. Manufacturer data is model- and configuration-specific, not a universal fact about a machine family.
8. Commercial pages must prove scope, competent personnel, equipment access, insurance/warranty boundaries, and service geography. Replace unsupported superlatives and trust claims with verifiable evidence.
9. Original photos require project permission, date, machine/configuration, task, and safety context. Stock images do not prove experience.
10. Review volatile regulatory, availability, price, technology, and emissions statements at least annually and whenever the underlying primary source changes.

## First bounded publication cluster

Wave `W1-foundation-safety` contains 12 assets:

1. ABR-01-01 — central project guide.
2. ABR-01-02 — function-based classification.
3. ABR-02-01 — site and task survey.
4. ABR-03-01 — earthmoving machine role comparison.
5. ABR-04-01 — lifting-equipment family selection.
6. ABR-07-01 — heavy-equipment transport method comparison.
7. ABR-09-01 — attachment compatibility.
8. ABR-11-01 — equipment-specific K3 plan.
9. ABR-12-01 — ground bearing and support variables.
10. ABR-13-01 — rent-versus-buy decision.
11. ABR-15-01 — layered pre-start inspection.
12. ABR-17-01 — spill prevention and response.

The cluster forms one decision path: understand the machine universe → survey and choose → prepare the main work families → verify transport/attachment/ground/K3 constraints → procure → inspect → control environmental harm. Each asset links upward to the central hub, sideways to its immediate decision partner, and to a commercial route only where a qualified next step exists.

Monitor final-URL indexation, impressions grouped by task intent, clicks into related decision pages, checklist/tool completion, qualified quotation requests, recurring safety exits, and GSC signs that two same-domain pages compete for the same query. Ranking alone is not the success condition.

## Definition of done

- All 18 topic hubs and 108 article briefs have a published or explicitly deferred owner.
- Every published safety, load, transport, engineering, environmental, and regulatory claim passes its evidence and competent-review gate.
- Every article answers one primary job, links to its hub, has context-specific related links, and does not duplicate another `alat.berat.id` page's intent.
- Sitemap and canonical audits resolve the 1,637 trailing-slash duplicate groups, malformed placeholder, and `.html`/directory ambiguity without discarding useful history blindly.
- Location and route pages are retained only with verified unique value; city-name substitution is not considered completion.
- Commercial claims, prices, availability, licenses, certifications, and case studies are current and evidenced.
- Baseline and post-publication measurements include indexation, task-intent impressions, reader completion, qualified leads, and cannibalization checks.
