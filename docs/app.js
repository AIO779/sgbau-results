// ── Config ─────────────────────────────────────────────────────────────────────
const API_URL = "https://sgbau-results.onrender.com";   // ← change to Render URL in Phase 10

// ── State ──────────────────────────────────────────────────────────────────────
let currentJobId  = null;
let totalRolls    = 0;
let countReceived = 0;
let allRows       = [];
let pillFilter    = "all";

// ── SGBAU Course Catalog (value → { label, abbr }) ────────────────────────────
// Extracted verbatim from the university's result page HTML.
const COURSES = [
  { value: "C000058", label: "B.Arch — Bachelor of Architecture CBCS",                          abbr: "B.Arch"    },
  { value: "C000087", label: "B.COM(Acc&Fin) — B.COM. Accounting & Finance NEP",                abbr: "BCOM-AF"   },
  { value: "C000266", label: "B.E.(AI&DS) — Artificial Intelligence & Data Sciences NEP",       abbr: "AI&DS"     },
  { value: "C000045", label: "B.E.(Chem. Engg) — Chemical Engineering NEP",                     abbr: "CHEM"      },
  { value: "C000032", label: "B.E.(CSE) — Computer Science & Engineering NEP",                  abbr: "CSE"       },
  { value: "C000317", label: "B.E.(CSE-DS) — Computer Science & Engineering (Data Science) NEP",abbr: "CSE-DS"    },
  { value: "C000314", label: "BE in IOT — Internet Of Things",                                  abbr: "IOT"       },
  { value: "C000037", label: "B.E.(ETC) — Electronics & Telecommunication Engg. NEP",           abbr: "EXTC"      },
  { value: "C000038", label: "B.E.(EC&E) — Electronics Engineering CGS",                        abbr: "ECE"       },
  { value: "C000043", label: "B.E.(Elec. Pow.) — Electronics & Power NEP",                      abbr: "EP"        },
  { value: "C000034", label: "B.E.(EE) — Electrical Engineering NEP",                           abbr: "EE"        },
  { value: "C000033", label: "B.E.(EEE) — Electrical & Electronics Engineering CGS",            abbr: "EEE"       },
  { value: "C000039", label: "B.E.(IT) — Information Technology NEP",                           abbr: "IT"        },
  { value: "C000040", label: "B.E.(Instr. Engg) — Instrumentation Engineering CGS",             abbr: "INSTR"     },
  { value: "C000041", label: "B.E.(ME) — Mechanical Engineering NEP",                           abbr: "MECH"      },
  { value: "C000042", label: "B.E.(Prod. Engg) — Production Engineering CGS",                   abbr: "PROD"      },
  { value: "C000031", label: "B.E.(CIVIL ENGG) — Civil Engineering NEP",                        abbr: "CIVIL"     },
  { value: "C000027", label: "B.E.(Comp.Engg) — Computer Engineering NEP",                      abbr: "COMP"      },
  { value: "C000030", label: "B.E.(BIOMEDICAL ENGG) — Biomedical Engineering CGS",              abbr: "BME"       },
  { value: "C000029", label: "B.E.(B.SC HOLDER) — B.E. for B.Sc Holders",                      abbr: "BE-BSC"    },
  { value: "C000048", label: "B.E.(First Year) — B.E. First Year NEP",                          abbr: "BE-FY"     },
  { value: "C000015", label: "B.H.Sc. — B.SC. Home Science NEP",                                abbr: "HSC"       },
  { value: "C000050", label: "B.Tech(Chem.Tech.All) — Chemical Technology First Year NEP",      abbr: "CT-FY"     },
  { value: "C000053", label: "B.Tech(Chem.Tech.Food) — Chemical Technology Food Technology NEP",abbr: "CT-FOOD"   },
  { value: "C000054", label: "B.Tech(Chem.Tech.Oil) — Chemical Technology Oil & Paint NEP",     abbr: "CT-OIL"    },
  { value: "C000051", label: "B.Tech(Chem.Tech.Polymer) — Chemical Technology Polymer Group A", abbr: "CT-POL"    },
  { value: "C000056", label: "B.Tech(Chem.Tech.Pulp) — Chemical Technology Pulp & Paper NEP",   abbr: "CT-PULP"   },
  { value: "C000055", label: "B.Tech(Chem.Tech.Petro) — Chemical Technology PetroChemical NEP", abbr: "CT-PETRO"  },
  { value: "C000013", label: "B.Tech.COS — B.TECH. Cosmetics NEP",                              abbr: "COS"       },
  { value: "C000057", label: "B.Tech(Textile) — Textile Engineering NEP",                       abbr: "TEXT"      },
  { value: "C000376", label: "B.A.(Liberal Arts) — BA Liberal Arts NEP",                        abbr: "BA-LA"     },
  { value: "C000001", label: "BA — Bachelor of Arts",                                            abbr: "BA"        },
  { value: "C000007", label: "BASW — Bachelor of Arts in Social Work CBCS",                     abbr: "BASW"      },
  { value: "C000008", label: "BAJMC — Arts Journalism & Mass Communication NEP",                 abbr: "BAJMC"     },
  { value: "C000009", label: "BBA — Bachelor of Business Administration",                        abbr: "BBA"       },
  { value: "C000003", label: "BCOM — Bachelor Of Commerce",                                      abbr: "BCOM"      },
  { value: "C000331", label: "BCOM(BIS) — B.COM Business Information System",                   abbr: "BCOM-BIS"  },
  { value: "C000330", label: "BCOM(Mgmt) — B.COM Management & Entrepreneurship Dev.",           abbr: "BCOM-MGT"  },
  { value: "C000012", label: "BCA — Bachelor of Computer Application",                           abbr: "BCA"       },
  { value: "C000353", label: "B.Counselling — Bachelor of Counselling & Psychotherapy",         abbr: "BCP"       },
  { value: "C000204", label: "BED — Bachelor of Education",                                      abbr: "BED"       },
  { value: "C000014", label: "BFD — Bachelor of Fashion Designing",                              abbr: "BFD"       },
  { value: "C000182", label: "B.LIB — Bachelor of Library & Information Science",               abbr: "BLIB"      },
  { value: "C000115", label: "Bpharm — Bachelor of Pharmacy",                                    abbr: "BPHARM"    },
  { value: "C000227", label: "Pharm.D — Doctor of Pharmacy",                                     abbr: "PHARMD"    },
  { value: "C000010", label: "BPA — Bachelor of Performing Arts NEP",                            abbr: "BPA"       },
  { value: "C000202", label: "BPED — Bachelor of Physical Education",                            abbr: "BPED"      },
  { value: "C000006", label: "B.P.E.S. — Bachelor of Physical Education & Sports CBCS",         abbr: "BPES"      },
  { value: "C000002", label: "BSC — Bachelor Of Science",                                        abbr: "BSC"       },
  { value: "C000211", label: "BSC(Animation) — Bachelor of Science Animation CBCS",             abbr: "BSC-ANI"   },
  { value: "C000348", label: "BSC(DataSci) — Bachelor of Science Data Science & Analytics",     abbr: "BSC-DS"    },
  { value: "C000347", label: "BSC(CyberSec) — Bachelor of Science Cyber Security",              abbr: "BSC-CS"    },
  { value: "C000011", label: "BSW — Bachelor of Social Work CBCS",                               abbr: "BSW"       },
  { value: "C000378", label: "BCOMLLB — B.Com LL.B 5 Years",                                    abbr: "BCOMLLB"   },
  { value: "C000215", label: "LLB3 — Bachelor of Legislative Law 3 Years",                      abbr: "LLB3"      },
  { value: "C000005", label: "LLB5 — LL.B 5 Years",                                             abbr: "LLB5"      },
  { value: "C000256", label: "B.VOC(Cyber) — B. VOC IT/ITES/Cyber Security CGS NEW",           abbr: "VOC-CYB"   },
  { value: "C000232", label: "B.VOC(Acc&Tax) — B. VOC Accounting & Taxation CGS NEW",          abbr: "VOC-ACC"   },
  { value: "C000144", label: "B.VOC(Auto) — B. VOC Automobiles CGS NEW",                        abbr: "VOC-AUTO"  },
  { value: "C000146", label: "B.VOC(Cosmetic) — B. VOC Cosmetic Technology CGS NEW",           abbr: "VOC-COS"   },
  { value: "C000150", label: "B.VOC(Fashion) — B. VOC Fashion Tech & Apparel Designing CGS",   abbr: "VOC-FASH"  },
  { value: "C000153", label: "B.VOC(ForensicSc) — B. VOC Forensic Science CGS NEW",            abbr: "VOC-FOR"   },
  { value: "C000157", label: "B.VOC(MediEquip) — B. VOC Medical Equipment Tech CGS NEW",       abbr: "VOC-MED"   },
  { value: "C000166", label: "B.VOC(Photo) — B. VOC Photography & Videography CGS NEW",        abbr: "VOC-PHO"   },
  { value: "C000164", label: "B.VOC(VehTest) — B. VOC Vehicle Testing CGS NEW",                abbr: "VOC-VEH"   },
  { value: "C000267", label: "DYED — Diploma in Yoga Education",                                 abbr: "YOGA"      },
  { value: "C000345", label: "DIP-ACT — Diploma in Applied Computer Technology",                abbr: "DIP-ACT"   },
  { value: "C000329", label: "DIP-BA — Diploma in Business Analytics",                           abbr: "DIP-BA"    },
  { value: "C000346", label: "DIP-CyberSec — Diploma in Cyber Security NEP",                    abbr: "DIP-CYB"   },
  { value: "C000349", label: "DIP-DisaMgmt — Diploma in Disaster Management",                   abbr: "DIP-DIS"   },
  { value: "C000326", label: "DIP-Tourism — Diploma in Tourism & Heritage Management",          abbr: "DIP-TOU"   },
  { value: "C000025", label: "CHP — Chemical Processing",                                        abbr: "CHP"       },
  { value: "C000020", label: "DTP — Desk Top Publishing",                                        abbr: "DTP"       },
  { value: "C000018", label: "FBS — Food and Beverage Service",                                  abbr: "FBS"       },
  { value: "C000019", label: "HKP — House Keeping",                                              abbr: "HKP"       },
  { value: "C000016", label: "RSA — Retail Sales Associate",                                     abbr: "RSA"       },
  { value: "C000026", label: "STG — Soil Testing",                                               abbr: "STG"       },
  { value: "C000021", label: "TAL — Tally",                                                      abbr: "TAL"       },
  { value: "C000024", label: "TSG — Textile Spinning",                                           abbr: "TSG"       },
  { value: "C000022", label: "TWG — Textile Weaving",                                            abbr: "TWG"       },
];

// ── Dept presets (command_generator.html PRESETS) ──────────────────────────────
// Maps course code → roll-number prefix hint (25XX310)
const PRESETS = {
  "C000032": { name: "CSE",    prefix: "25BD310" },
  "C000039": { name: "IT",     prefix: "25BI310" },
  "C000317": { name: "CSE-DS", prefix: "25LS310" },
  "C000037": { name: "EXTC",   prefix: "25BG310" },
  "C000034": { name: "EE",     prefix: "25BF310" },
  "C000031": { name: "CIVIL",  prefix: "25BC310" },
  "C000027": { name: "COMP",   prefix: "25BE310" },
  "C000041": { name: "MECH",   prefix: "25BM310" },
};

// ── Build course <options> HTML string once ───────────────────────────────────
const COURSE_OPTIONS = COURSES.map(
  c => `<option value="${c.value}">${c.label}</option>`
).join("");

// ── Department management ──────────────────────────────────────────────────────

function addDept() {
  const list = document.getElementById("dept-list");
  const idx  = Date.now(); // unique ID per row
  const row  = document.createElement("div");
  row.className   = "dept-row";
  row.dataset.idx = idx;

  row.innerHTML = `
    <div class="field dept-field-course">
      <label>Course</label>
      <div class="select-wrap">
        <select class="d-course" onchange="onCourseChange(this, '${idx}')">
          <option value="">— Select course —</option>
          ${COURSE_OPTIONS}
        </select>
      </div>
    </div>
    <div class="field">
      <label>Dept name</label>
      <input type="text" class="d-name" placeholder="e.g. CSE" />
    </div>
    <div class="field">
      <label>Start roll</label>
      <input type="text" class="d-start" placeholder="25BD310527" />
    </div>
    <div class="field">
      <label>End roll</label>
      <input type="text" class="d-end" placeholder="25BD310927" />
    </div>
    <button class="remove-btn" onclick="this.closest('.dept-row').remove()" title="Remove">✕</button>
  `;
  list.appendChild(row);
}

function onCourseChange(selectEl, idx) {
  const row    = document.querySelector(`.dept-row[data-idx="${idx}"]`);
  const code   = selectEl.value;
  const course = COURSES.find(c => c.value === code);
  if (!course) return;

  // Auto-fill dept name from abbreviation
  const nameInput = row.querySelector(".d-name");
  if (!nameInput.value) {
    nameInput.value = PRESETS[code]?.name || course.abbr;
  }

  // Auto-fill roll prefix hint if inputs are still empty / only a prefix
  const startInput = row.querySelector(".d-start");
  const endInput   = row.querySelector(".d-end");
  const prefix     = PRESETS[code]?.prefix;
  if (prefix) {
    if (!startInput.value) startInput.value = prefix;
    if (!endInput.value)   endInput.value   = prefix;
    // Place cursor at end so user just types the suffix
    [startInput, endInput].forEach(inp => {
      inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length);
    });
  }
}

function getDepts() {
  return [...document.querySelectorAll(".dept-row")].map(row => ({
    name:       row.querySelector(".d-name").value.trim(),
    start_roll: row.querySelector(".d-start").value.trim(),
    end_roll:   row.querySelector(".d-end").value.trim(),
    course_cd:  row.querySelector(".d-course").value.trim(),
  })).filter(d => d.name && d.start_roll && d.end_roll && d.course_cd);
}

// ── Fetch flow ─────────────────────────────────────────────────────────────────

async function startFetch() {
  const depts = getDepts();
  if (!depts.length) {
    alert("Please add at least one department with all fields filled in (including a course selection).");
    return;
  }

  // Reset UI
  allRows       = [];
  countReceived = 0;
  document.getElementById("results-body").innerHTML          = "";
  document.getElementById("summary-body").innerHTML          = "";
  document.getElementById("class-report-container").innerHTML = "";
  document.getElementById("results-count-badge").textContent  = "0";
  hide("results-card");
  hide("summary-card");
  hide("class-report-section");
  hide("download-btn");
  resetPills();

  const btn = document.getElementById("fetch-btn");
  btn.disabled = true;
  document.getElementById("fetch-btn-text").textContent = "Fetching…";

  setProgress("Waking up server (first request may take 30 s on free tier)…", 0);
  show("progress-card");

  try {
    const res = await fetch(`${API_URL}/api/fetch-results`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        departments: depts,
        session:     document.getElementById("session").value,
        sem_code:    document.getElementById("sem_code").value,
        result_type: document.getElementById("result_type").value,
        workers:     parseInt(document.getElementById("workers").value, 10) || 50,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Server error" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data   = await res.json();
    currentJobId = data.job_id;
    totalRolls   = data.total_rolls || 0;

    setProgress(`Job started — 0 / ${totalRolls} fetched`, 0);
    openSSE(currentJobId);

  } catch (err) {
    alert(`❌ Error starting job: ${err.message}`);
    hide("progress-card");
    resetFetchBtn();
  }
}

// ── SSE stream ─────────────────────────────────────────────────────────────────

function openSSE(jobId) {
  const es = new EventSource(`${API_URL}/api/progress/${jobId}`);

  es.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }

    if (msg.type === "result") {
      countReceived++;
      const pct = totalRolls > 0 ? Math.round((countReceived / totalRolls) * 100) : 0;
      setProgress(`Fetching… ${countReceived} / ${totalRolls} (${pct}%)`, pct);
      document.getElementById("progress-count").textContent = countReceived;
      appendResultRow(msg);
      show("results-card");

    } else if (msg.type === "done") {
      es.close();
      setProgress(`✅ Done — ${countReceived} results fetched`, 100);
      document.getElementById("progress-count").textContent = countReceived;
      renderSummary(msg.summary || []);
      renderClassReports(msg.summary || []);
      show("download-btn");
      show("summary-card");
      resetFetchBtn();

    } else if (msg.type === "error") {
      es.close();
      alert(`Scraper error: ${msg.message}`);
      hide("progress-card");
      resetFetchBtn();

    } else if (msg.type === "timeout") {
      es.close();
      alert("Connection timed out. Results collected so far are shown above.");
      resetFetchBtn();
    }
  };

  es.onerror = () => {
    es.close();
    alert("Lost connection to the server. Results collected so far are shown above.");
    resetFetchBtn();
  };
}

// ── Table rendering ────────────────────────────────────────────────────────────

function appendResultRow(msg) {
  const resultText = (msg.result || "").toUpperCase();
  const badgeClass =
    resultText === "PASS" ? "pass" :
    resultText === "FAIL" ? "fail" :
    resultText === "ATKT" ? "atkt" : "other";

  const rowData = {
    dept: msg.dept || "", roll: msg.roll || "", name: msg.name || "—",
    result: msg.result || "—", sgpa: msg.sgpa || "—",
    status: msg.status || "", badgeClass, resultText,
  };
  allRows.push(rowData);
  document.getElementById("results-count-badge").textContent = allRows.length;

  if (rowMatchesFilter(rowData)) renderRow(rowData);
}

function renderRow(d) {
  const tbody = document.getElementById("results-body");
  const tr    = document.createElement("tr");
  tr.dataset.result = d.resultText;
  tr.dataset.name   = d.name.toLowerCase();
  tr.dataset.roll   = d.roll.toLowerCase();
  tr.innerHTML = `
    <td>${d.dept}</td>
    <td><code style="font-size:12px;color:var(--indigo-400)">${d.roll}</code></td>
    <td>${d.name}</td>
    <td><span class="badge ${d.badgeClass}">${d.result}</span></td>
    <td>${d.sgpa}</td>
    <td><span style="font-size:12px;color:var(--text-muted)">${d.status}</span></td>
  `;
  tbody.appendChild(tr);
}

// ── Client-side filtering ──────────────────────────────────────────────────────

function rowMatchesFilter(d) {
  const q      = document.getElementById("filter-input").value.toLowerCase();
  const textOk = !q || d.name.toLowerCase().includes(q) || d.roll.toLowerCase().includes(q);
  const pillOk = pillFilter === "all" || d.resultText.toLowerCase() === pillFilter;
  return textOk && pillOk;
}

function filterTable() { rebuildTable(); }

function setPillFilter(val, el) {
  pillFilter = val;
  document.querySelectorAll(".pill").forEach(p => p.classList.remove("active"));
  el.classList.add("active");
  rebuildTable();
}

function resetPills() {
  pillFilter = "all";
  document.querySelectorAll(".pill").forEach(p => p.classList.remove("active"));
  document.querySelector('.pill[data-filter="all"]').classList.add("active");
}

function rebuildTable() {
  document.getElementById("results-body").innerHTML = "";
  allRows.filter(rowMatchesFilter).forEach(renderRow);
}

// ── Summary ────────────────────────────────────────────────────────────────────

function renderSummary(summaries) {
  const el = document.getElementById("summary-body");
  if (!summaries.length) { el.textContent = "No summary data."; return; }
  el.innerHTML = summaries.map(s => {
    const pct    = s.total > 0 ? Math.round((s.passed / s.total) * 100) : 0;
    const failed = s.total - s.passed;
    return `
      <div class="summary-item">
        <div class="summary-dept">${s.name}</div>
        <div class="summary-stat">📚 ${s.total} students &nbsp;·&nbsp; ${s.range || ""}</div>
        <div class="summary-stat" style="color:var(--pass);margin-top:6px">✓ ${s.passed} passed (${pct}%)</div>
        <div class="summary-stat" style="color:var(--fail)">✗ ${failed} failed</div>
        <div class="summary-bar-track">
          <div class="summary-bar-fill" style="width:${pct}%"></div>
        </div>
      </div>`;
  }).join("");
}

// ── Class Report rendering ───────────────────────────────────────────────────────────────

function renderClassReports(summaries) {
  const container = document.getElementById("class-report-container");

  const reports = summaries.filter(s => s.class_report && s.class_report.total_students > 0);
  if (!reports.length) return;

  container.innerHTML = reports.map(s => {
    const r       = s.class_report;
    const failPct = r.total_students > 0 ? (100 - r.pass_pct).toFixed(1) : "0.0";

    // ── Top-5 rows ──────────────────────────────────────────────────────────
    const rankClass = i => i === 1 ? "gold" : i === 2 ? "silver" : i === 3 ? "bronze" : "";
    const top5Html  = r.top5.length ? `
      <p class="report-section-title">🏆 Top 5 Students by SGPA</p>
      <ul class="report-top5">
        ${r.top5.map(st => `
          <li class="report-top5-item">
            <span class="report-rank ${rankClass(st.rank)}">${st.rank}</span>
            <span class="report-top5-name">${st.name}</span>
            <span class="report-top5-roll">${st.roll}</span>
            <span class="report-top5-sgpa">${st.sgpa.toFixed(2)}</span>
          </li>`).join("")}
      </ul>` : "";

    // ── Compute overall subject totals ──────────────────────────────────────
    const totalSubjStudents = r.subject_stats.reduce((a, b) => a + b.total,  0);
    const totalSubjPassed   = r.subject_stats.reduce((a, b) => a + b.passed, 0);
    const totalSubjFailed   = r.subject_stats.reduce((a, b) => a + b.failed, 0);
    const overallPassPct    = totalSubjStudents > 0
      ? ((totalSubjPassed / totalSubjStudents) * 100).toFixed(1) : "0.0";
    const overallFailPct    = totalSubjStudents > 0
      ? ((totalSubjFailed / totalSubjStudents) * 100).toFixed(1) : "0.0";

    // ── Subject stats table ─────────────────────────────────────────────────
    const subjHtml = r.subject_stats.length ? `
      <p class="report-section-title">📚 Subject-wise Results</p>
      <div class="report-table-wrap">
        <table class="report-subj-table">
          <thead>
            <tr>
              <th class="col-subj">Subject</th>
              <th class="col-num">Total</th>
              <th class="col-num">Passed</th>
              <th class="col-pct">Pass %</th>
              <th class="col-num">Failed</th>
              <th class="col-pct">Fail %</th>
              <th class="col-bar">Pass Rate</th>
            </tr>
          </thead>
          <tbody>
            <!-- Overall semester row -->
            <tr class="subj-overall-row">
              <td class="col-subj"><strong>Overall Semester</strong></td>
              <td class="col-num"><strong>${r.total_students}</strong></td>
              <td class="col-num pass-num"><strong>${r.passed}</strong></td>
              <td class="col-pct pass-pct"><strong>${r.pass_pct}%</strong></td>
              <td class="col-num fail-num"><strong>${r.failed}</strong></td>
              <td class="col-pct fail-pct"><strong>${failPct}%</strong></td>
              <td class="col-bar">
                <div class="subj-bar-wrap">
                  <div class="subj-bar-track">
                    <div class="subj-bar-pass" style="width:${r.pass_pct}%"></div>
                  </div>
                  <span class="bar-label">${r.pass_pct}%</span>
                </div>
              </td>
            </tr>
            <!-- Per-subject rows -->
            ${r.subject_stats.map(sub => `
            <tr>
              <td class="col-subj"><strong>${sub.subject}</strong></td>
              <td class="col-num">${sub.total}</td>
              <td class="col-num pass-num">${sub.passed}</td>
              <td class="col-pct pass-pct">${sub.pass_pct}%</td>
              <td class="col-num fail-num">${sub.failed}</td>
              <td class="col-pct fail-pct">${sub.fail_pct}%</td>
              <td class="col-bar">
                <div class="subj-bar-wrap">
                  <div class="subj-bar-track">
                    <div class="subj-bar-pass" style="width:${sub.pass_pct}%"></div>
                  </div>
                  <span class="bar-label">${sub.pass_pct}%</span>
                </div>
              </td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>` : "";

    return `
      <div class="report-card">
        <div class="report-card-header">
          <span class="report-dept-name">${r.dept}</span>
        </div>
        <div class="report-overview">
          <span class="report-stat-pill total">👥 ${r.total_students} Students</span>
          <span class="report-stat-pill passed">✓ ${r.passed} Passed &nbsp;(${r.pass_pct}%)</span>
          <span class="report-stat-pill failed">✗ ${r.failed} Failed &nbsp;(${failPct}%)</span>
        </div>
        ${top5Html}
        ${subjHtml}
      </div>`;
  }).join("");

  show("class-report-section");
}

// ── CSV download ───────────────────────────────────────────────────────────────

function downloadCSV() {
  if (!currentJobId) return;
  window.open(`${API_URL}/api/download/${currentJobId}`, "_blank");
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function setProgress(label, pct) {
  document.getElementById("progress-label").textContent = label;
  document.getElementById("progress-fill").style.width  = `${Math.min(pct, 100)}%`;
}

function resetFetchBtn() {
  const btn = document.getElementById("fetch-btn");
  btn.disabled = false;
  document.getElementById("fetch-btn-text").textContent = "Fetch Results";
}

function show(id) { document.getElementById(id)?.classList.remove("hidden"); }
function hide(id) { document.getElementById(id)?.classList.add("hidden"); }

// ── Init ───────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => addDept());
