import { ChangeEvent, DragEvent, useEffect, useMemo, useState } from "react";
import { api, jsonRequest } from "./api";
import type {
  ExtractedRequirements,
  HardConstraints,
  InlineResume,
  MatchResult,
  Requirement,
  RequirementKind,
  SavedResume,
} from "./types";

type CriteriaSource = "generated" | "manual" | "json";

type UploadResponse =
  | { saved: true; resume: SavedResume; security_flags: string[] }
  | {
      saved: false;
      resume: InlineResume & { size_bytes: number };
      security_flags: string[];
    };

const supportedResumeExtensions = [".pdf", ".docx", ".txt"];

const emptyConstraints = {
  min_years_experience: null,
  required_degree: null,
  location: null,
  remote: null,
};

const requirementsJsonPlaceholder = `{
  "requirements": [
    {
      "id": "r1",
      "text": "3+ years building production ML systems",
      "kind": "must_have",
      "weight": 3
    }
  ],
  "hard_constraints": {
    "min_years_experience": 3,
    "required_degree": null,
    "location": null,
    "remote": true
  }
}`;

function bytes(value: number) {
  return value < 1024 * 1024
    ? `${Math.ceil(value / 1024)} KB`
    : `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function resultColor(score: number) {
  return score >= 80
    ? "bg-emerald-500"
    : score >= 55
      ? "bg-amber-400"
      : "bg-rose-500";
}

export default function App() {
  const [dark, setDark] = useState(() => localStorage.theme === "dark");
  const [tab, setTab] = useState<"upload" | "library">("upload");
  const [library, setLibrary] = useState<SavedResume[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [inlineResumes, setInlineResumes] = useState<InlineResume[]>([]);
  const [saveUpload, setSaveUpload] = useState(false);
  const [jdUrl, setJdUrl] = useState("");
  const [jdText, setJdText] = useState("");
  const [extracted, setExtracted] = useState<ExtractedRequirements | null>(
    null,
  );
  const [criteriaSource, setCriteriaSource] = useState<CriteriaSource | null>(
    null,
  );
  const [requirementsJson, setRequirementsJson] = useState("");
  const [results, setResults] = useState<MatchResult[]>([]);
  const [activeResult, setActiveResult] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.theme = dark ? "dark" : "light";
  }, [dark]);

  const refreshLibrary = async () => {
    try {
      setLibrary(await api<SavedResume[]>("/resumes"));
    } catch (cause) {
      setError((cause as Error).message);
    }
  };
  useEffect(() => void refreshLibrary(), []);

  const selectedCount = selectedIds.length + inlineResumes.length;
  const canScore =
    selectedCount > 0 &&
    Boolean(extracted?.requirements.length) &&
    Boolean(
      extracted?.requirements.every((item) => item.text.trim().length >= 2),
    );
  const detail = results[activeResult];

  async function uploadFiles(files: File[]) {
    const supported = files.filter((file) =>
      supportedResumeExtensions.some((extension) =>
        file.name.toLowerCase().endsWith(extension),
      ),
    );
    const skipped = files.length - supported.length;
    if (!supported.length) {
      setError("No supported resumes found. Choose PDF, DOCX, or TXT files.");
      return;
    }

    setError(null);
    setNotice(null);
    const saved: SavedResume[] = [];
    const inline: InlineResume[] = [];
    const failures: string[] = [];
    const sanitized: string[] = [];
    try {
      for (const [index, file] of supported.entries()) {
        const displayName = (file.webkitRelativePath || file.name).slice(
          0,
          255,
        );
        setBusy(`Reading ${index + 1} of ${supported.length}: ${displayName}`);
        try {
          const form = new FormData();
          form.append("file", file);
          form.append("save", String(saveUpload));
          form.append("name", displayName);
          const response = await api<UploadResponse>("/resumes", {
            method: "POST",
            body: form,
          });
          if (response.security_flags.length) {
            sanitized.push(
              `${displayName}: ${response.security_flags.join(", ")}`,
            );
          }
          if (response.saved) {
            saved.push(response.resume);
          } else {
            inline.push({
              name: response.resume.name,
              text: response.resume.text,
            });
          }
        } catch (cause) {
          failures.push(`${displayName}: ${(cause as Error).message}`);
        }
      }

      if (saved.length) {
        setLibrary((current) => [...saved.reverse(), ...current]);
        setSelectedIds((current) => [
          ...new Set([...current, ...saved.map((resume) => resume.id)]),
        ]);
      }
      if (inline.length) {
        setInlineResumes((current) => [...current, ...inline]);
      }
      if (saved.length || inline.length) {
        setResults([]);
        const added = saved.length + inline.length;
        setNotice(
          `${added} resume${added === 1 ? "" : "s"} ready to score${
            skipped
              ? `; ${skipped} unsupported file${skipped === 1 ? " was" : "s were"} skipped`
              : ""
          }.${
            sanitized.length
              ? ` Security sanitation was applied to ${sanitized.length} file${sanitized.length === 1 ? "" : "s"}: ${sanitized.slice(0, 3).join("; ")}.`
              : ""
          }`,
        );
      }
      if (failures.length) {
        const shownFailures = failures.slice(0, 5);
        const moreFailures = failures.length - shownFailures.length;
        setError(
          `${failures.length} file${failures.length === 1 ? "" : "s"} could not be added: ${shownFailures.join("; ")}${moreFailures ? `; and ${moreFailures} more` : ""}`,
        );
      }
    } finally {
      setBusy(null);
    }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    await uploadFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  async function uploadFolder(event: ChangeEvent<HTMLInputElement>) {
    await uploadFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  async function dropUpload(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    await uploadFiles(Array.from(event.dataTransfer.files));
  }

  async function fetchJD() {
    if (!jdUrl.trim()) return;
    setBusy("Fetching job posting");
    setError(null);
    try {
      const response = await api<{ text: string }>(
        "/jd/fetch",
        jsonRequest({ url: jdUrl }),
      );
      setJdText(response.text);
      setExtracted(null);
      setCriteriaSource(null);
      setResults([]);
    } catch (cause) {
      setError(
        `${(cause as Error).message} You can paste the description below.`,
      );
    } finally {
      setBusy(null);
    }
  }

  async function extractRequirements() {
    if (!jdText.trim()) return;
    setBusy("Extracting requirements");
    setError(null);
    try {
      const response = await api<ExtractedRequirements>(
        "/jd/requirements",
        jsonRequest({ jd_text: jdText }),
      );
      setExtracted(response);
      setCriteriaSource("generated");
      setResults([]);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  }

  function startManualCriteria() {
    setError(null);
    setNotice(null);
    setCriteriaSource("manual");
    setResults([]);
    setExtracted({
      requirements: [
        {
          id: "r1",
          text: "Required skill or experience",
          kind: "skill",
          weight: 1,
        },
      ],
      hard_constraints: { ...emptyConstraints },
    });
  }

  async function importRequirements() {
    if (!requirementsJson.trim()) return;
    setBusy("Validating requirements JSON");
    setError(null);
    setNotice(null);
    try {
      const withoutFence = requirementsJson
        .trim()
        .replace(/^```(?:json)?\s*/i, "")
        .replace(/\s*```$/, "");
      const payload = JSON.parse(withoutFence) as unknown;
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        throw new Error(
          "The JSON root must be an ExtractedRequirements object.",
        );
      }
      const response = await api<ExtractedRequirements>(
        "/requirements/validate",
        jsonRequest(payload),
      );
      setExtracted(response);
      setCriteriaSource("json");
      setResults([]);
      setNotice(
        `Loaded ${response.requirements.length} validated requirement${response.requirements.length === 1 ? "" : "s"}.`,
      );
    } catch (cause) {
      const message = (cause as Error).message;
      setError(
        cause instanceof SyntaxError
          ? `Invalid requirements JSON: ${message}`
          : message,
      );
    } finally {
      setBusy(null);
    }
  }

  function updateRequirement(index: number, patch: Partial<Requirement>) {
    if (!extracted) return;
    const requirements = extracted.requirements.map((item, i) =>
      i === index ? { ...item, ...patch } : item,
    );
    setExtracted({ ...extracted, requirements });
    setResults([]);
  }

  function updateHardConstraints(patch: Partial<HardConstraints>) {
    if (!extracted) return;
    setExtracted({
      ...extracted,
      hard_constraints: { ...extracted.hard_constraints, ...patch },
    });
    setResults([]);
  }

  function addRequirement() {
    if (!extracted) return;
    const usedIds = new Set(extracted.requirements.map((item) => item.id));
    let suffix = extracted.requirements.length + 1;
    while (usedIds.has(`r${suffix}`)) suffix += 1;
    const next = `r${suffix}`;
    setExtracted({
      ...extracted,
      requirements: [
        ...extracted.requirements,
        { id: next, text: "New requirement", kind: "skill", weight: 1 },
      ],
    });
    setResults([]);
  }

  async function runMatch() {
    if (!extracted) return;
    setBusy(`Scoring ${selectedCount} resume${selectedCount === 1 ? "" : "s"}`);
    setError(null);
    setNotice(null);
    setResults([]);
    try {
      const response = await api<{ results: MatchResult[] }>(
        "/match",
        jsonRequest({
          resume_ids: selectedIds,
          resumes: inlineResumes,
          requirements: extracted.requirements,
          hard_constraints: extracted.hard_constraints,
          include_evidence: true,
        }),
      );
      setResults(response.results);
      setActiveResult(0);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  }

  function exportCSV() {
    const rows = [
      [
        "rank",
        "resume",
        "status",
        "score",
        "verdict",
        "human_review",
        "rejection_reasons",
      ],
      ...results.map((result, index) => [
        result.status === "scored" ? String(index + 1) : "",
        result.resume_name,
        result.status,
        result.status === "scored" ? String(result.match_score ?? 0) : "",
        result.verdict,
        String(result.requires_human_review),
        result.rejection_reasons.join("; "),
      ]),
    ];
    const csv = rows
      .map((row) =>
        row.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(","),
      )
      .join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    link.download = "jevmatch-results.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  const progress = useMemo(() => {
    if (results.length) return 3;
    if (extracted) return 2;
    if (selectedCount || jdText) return 1;
    return 0;
  }, [results, extracted, selectedCount, jdText]);

  return (
    <div className="min-h-screen bg-paper text-ink transition-colors dark:bg-[#0c1314] dark:text-stone-100">
      <header className="border-b border-black/10 dark:border-white/10">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-ink text-sm font-black text-acid dark:bg-acid dark:text-ink">
              JM
            </div>
            <div>
              <p className="font-display text-lg font-extrabold leading-none">
                JevMatch
              </p>
              <p className="mt-1 text-xs text-stone-500">
                Decision support, not decision maker
              </p>
            </div>
          </div>
          <button
            className="button-secondary"
            onClick={() => setDark(!dark)}
            aria-label="Toggle color theme"
          >
            {dark ? "Light" : "Dark"} mode
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-5 py-10 lg:px-8">
        <section className="mb-10 grid gap-8 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="max-w-3xl">
            <p className="eyebrow">Transparent candidate comparison</p>
            <h1 className="mt-3 font-display text-4xl font-black tracking-[-0.045em] sm:text-6xl">
              Match evidence.
              <br />
              <span className="text-teal dark:text-acid">
                Keep humans in charge.
              </span>
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-stone-600 dark:text-stone-400">
              Turn a job description into editable criteria, compare one or many
              resumes, and inspect every score and gap.
            </p>
          </div>
          <ol className="flex gap-2" aria-label="Workflow progress">
            {["Resumes", "Criteria", "Results"].map((label, index) => (
              <li
                key={label}
                className={`step ${progress >= index + 1 ? "step-complete" : ""}`}
              >
                <span>{index + 1}</span>
                {label}
              </li>
            ))}
          </ol>
        </section>

        {error && (
          <div
            role="alert"
            className="mb-6 flex items-start justify-between rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200"
          >
            <span>{error}</span>
            <button onClick={() => setError(null)} aria-label="Dismiss">
              ×
            </button>
          </div>
        )}

        {notice && (
          <div
            role="status"
            className="mb-6 flex items-start justify-between rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
          >
            <span>{notice}</span>
            <button onClick={() => setNotice(null)} aria-label="Dismiss">
              ×
            </button>
          </div>
        )}

        <div className="grid gap-6 xl:grid-cols-2">
          <section className="panel">
            <div className="section-heading">
              <div>
                <span className="section-number">01</span>
                <h2>Choose resumes</h2>
              </div>
              <span className="count">{selectedCount} selected</span>
            </div>
            <div className="tabs">
              <button
                className={tab === "upload" ? "active" : ""}
                onClick={() => setTab("upload")}
              >
                Upload
              </button>
              <button
                className={tab === "library" ? "active" : ""}
                onClick={() => setTab("library")}
              >
                Saved library
              </button>
            </div>
            {tab === "upload" ? (
              <div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label
                    className="dropzone px-4"
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={dropUpload}
                  >
                    <input
                      type="file"
                      className="sr-only"
                      accept=".pdf,.docx,.txt"
                      onChange={upload}
                    />
                    <span className="text-3xl">↥</span>
                    <strong>Upload one resume</strong>
                    <small>Browse, or drop one or more files here</small>
                  </label>
                  <label className="dropzone px-4">
                    <input
                      type="file"
                      className="sr-only"
                      accept=".pdf,.docx,.txt"
                      multiple
                      ref={(input) => {
                        if (input) input.setAttribute("webkitdirectory", "");
                      }}
                      onChange={uploadFolder}
                    />
                    <span className="text-3xl">▤</span>
                    <strong>Choose a resume folder</strong>
                    <small>All PDF, DOCX, and TXT files · 5 MB each</small>
                  </label>
                </div>
                <label className="mt-4 flex items-center gap-2 text-sm text-stone-600 dark:text-stone-300">
                  <input
                    type="checkbox"
                    checked={saveUpload}
                    onChange={(event) => setSaveUpload(event.target.checked)}
                  />
                  Save to my local library
                </label>
                {inlineResumes.map((resume, index) => (
                  <div
                    className="resume-row mt-3"
                    key={`${resume.name}-${index}`}
                  >
                    <div className="min-w-0 flex-1">
                      <strong className="block truncate" title={resume.name}>
                        {resume.name}
                      </strong>
                      <small>Ready for this session</small>
                    </div>
                    <button
                      onClick={() => {
                        setInlineResumes((current) =>
                          current.filter((_, i) => i !== index),
                        );
                        setResults([]);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {library.length === 0 && (
                  <p className="empty">No saved resumes yet.</p>
                )}
                {library.map((resume) => (
                  <label className="resume-row cursor-pointer" key={resume.id}>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(resume.id)}
                      onChange={(event) => {
                        setSelectedIds((current) =>
                          event.target.checked
                            ? [...new Set([...current, resume.id])]
                            : current.filter((id) => id !== resume.id),
                        );
                        setResults([]);
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <strong className="block truncate">{resume.name}</strong>
                      <small>
                        {bytes(resume.size_bytes)} ·{" "}
                        {new Date(resume.created_at).toLocaleDateString()}
                      </small>
                    </div>
                    <button
                      type="button"
                      onClick={async (event) => {
                        event.preventDefault();
                        const name = window
                          .prompt("Resume name", resume.name)
                          ?.trim();
                        if (!name) return;
                        await api(`/resumes/${resume.id}`, {
                          method: "PATCH",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ name }),
                        });
                        void refreshLibrary();
                      }}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      onClick={async (event) => {
                        event.preventDefault();
                        await api(`/resumes/${resume.id}`, {
                          method: "DELETE",
                        });
                        setSelectedIds((current) =>
                          current.filter((id) => id !== resume.id),
                        );
                        setResults([]);
                        void refreshLibrary();
                      }}
                    >
                      Delete
                    </button>
                  </label>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <div className="section-heading">
              <div>
                <span className="section-number">02</span>
                <h2>Add the job</h2>
              </div>
            </div>
            <label className="label" htmlFor="jd-url">
              Job-posting link
            </label>
            <div className="flex gap-2">
              <input
                id="jd-url"
                className="input flex-1"
                placeholder="https://company.com/jobs/…"
                value={jdUrl}
                onChange={(event) => setJdUrl(event.target.value)}
              />
              <button
                className="button-secondary"
                disabled={!jdUrl || Boolean(busy)}
                onClick={fetchJD}
              >
                Fetch
              </button>
            </div>
            <div className="my-4 flex items-center gap-3 text-xs uppercase tracking-widest text-stone-400">
              <span className="h-px flex-1 bg-black/10 dark:bg-white/10" />
              or paste text
              <span className="h-px flex-1 bg-black/10 dark:bg-white/10" />
            </div>
            <textarea
              className="input min-h-48 resize-y"
              placeholder="Paste the complete job description here…"
              value={jdText}
              onChange={(event) => {
                setJdText(event.target.value);
                setExtracted(null);
                setCriteriaSource(null);
                setResults([]);
              }}
            />
            <button
              className="button-primary mt-4 w-full"
              disabled={jdText.trim().length < 20 || Boolean(busy)}
              onClick={extractRequirements}
            >
              Build editable criteria
            </button>
            <div className="my-4 flex items-center gap-3 text-xs uppercase tracking-widest text-stone-400">
              <span className="h-px flex-1 bg-black/10 dark:bg-white/10" />
              or skip Anthropic
              <span className="h-px flex-1 bg-black/10 dark:bg-white/10" />
            </div>
            <button
              className="button-secondary w-full"
              disabled={Boolean(busy)}
              onClick={startManualCriteria}
            >
              Enter criteria manually
            </button>
            <details className="mt-3 rounded-xl border border-black/10 p-4 dark:border-white/10">
              <summary className="cursor-pointer text-sm font-bold">
                Paste ExtractedRequirements JSON
              </summary>
              <p className="mt-3 text-xs leading-5 text-stone-500 dark:text-stone-400">
                Paste the complete JSON object. It is validated by the local API
                and does not call Anthropic.
              </p>
              <textarea
                className="input mt-3 min-h-56 resize-y font-mono text-xs"
                aria-label="ExtractedRequirements JSON"
                placeholder={requirementsJsonPlaceholder}
                value={requirementsJson}
                onChange={(event) => setRequirementsJson(event.target.value)}
              />
              <button
                className="button-secondary mt-3 w-full"
                disabled={!requirementsJson.trim() || Boolean(busy)}
                onClick={importRequirements}
              >
                Validate and load JSON
              </button>
            </details>
          </section>
        </div>

        {extracted && (
          <section className="panel mt-6">
            <div className="section-heading">
              <div>
                <span className="section-number">03</span>
                <h2>Review criteria</h2>
              </div>
              <button className="button-secondary" onClick={addRequirement}>
                + Add criterion
              </button>
            </div>
            <p className="mb-5 text-sm text-stone-500">
              {criteriaSource === "manual"
                ? "Enter the criteria Jev should judge. No Anthropic call is needed."
                : criteriaSource === "json"
                  ? "The imported JSON passed server-side validation. Review or edit it before scoring."
                  : "These are generated once, cached locally, and fully editable before scoring."}
            </p>
            <div className="requirements-grid text-xs font-bold uppercase tracking-wider text-stone-400">
              <span>Requirement</span>
              <span>Kind</span>
              <span>Weight</span>
              <span />
            </div>
            <div className="divide-y divide-black/5 dark:divide-white/5">
              {extracted.requirements.map((item, index) => (
                <div
                  className="requirements-grid py-3"
                  key={`${item.id}-${index}`}
                >
                  <input
                    className="input"
                    value={item.text}
                    onChange={(event) =>
                      updateRequirement(index, { text: event.target.value })
                    }
                  />
                  <select
                    className="input"
                    value={item.kind}
                    onChange={(event) =>
                      updateRequirement(index, {
                        kind: event.target.value as RequirementKind,
                      })
                    }
                  >
                    <option value="must_have">Must-have</option>
                    <option value="skill">Skill</option>
                    <option value="nice_to_have">Nice-to-have</option>
                  </select>
                  <select
                    className="input"
                    value={item.weight}
                    onChange={(event) =>
                      updateRequirement(index, {
                        weight: Number(event.target.value),
                      })
                    }
                  >
                    <option value={1}>1 · Support</option>
                    <option value={2}>2 · Important</option>
                    <option value={3}>3 · Critical</option>
                  </select>
                  <button
                    className="remove"
                    aria-label="Delete requirement"
                    onClick={() => {
                      setExtracted({
                        ...extracted,
                        requirements: extracted.requirements.filter(
                          (_, i) => i !== index,
                        ),
                      });
                      setResults([]);
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-7 border-t border-black/10 pt-6 dark:border-white/10">
              <div className="mb-4">
                <h3 className="font-display text-lg font-black">
                  Hard constraints
                </h3>
                <p className="mt-1 text-xs text-stone-500">
                  Leave a field blank when it is not a strict filter.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <label>
                  <span className="label">Minimum total years</span>
                  <input
                    className="input"
                    type="number"
                    min="0"
                    max="80"
                    step="0.5"
                    value={
                      extracted.hard_constraints.min_years_experience ?? ""
                    }
                    onChange={(event) =>
                      updateHardConstraints({
                        min_years_experience: event.target.value
                          ? Number(event.target.value)
                          : null,
                      })
                    }
                  />
                </label>
                <label>
                  <span className="label">Required degree</span>
                  <select
                    className="input"
                    value={extracted.hard_constraints.required_degree ?? ""}
                    onChange={(event) =>
                      updateHardConstraints({
                        required_degree: (event.target.value ||
                          null) as HardConstraints["required_degree"],
                      })
                    }
                  >
                    <option value="">None</option>
                    <option value="associate">Associate</option>
                    <option value="bachelor">Bachelor</option>
                    <option value="master">Master</option>
                    <option value="doctorate">Doctorate</option>
                  </select>
                </label>
                <label>
                  <span className="label">Location</span>
                  <input
                    className="input"
                    maxLength={200}
                    placeholder="e.g. United States"
                    value={extracted.hard_constraints.location ?? ""}
                    onChange={(event) =>
                      updateHardConstraints({
                        location: event.target.value.trimStart() || null,
                      })
                    }
                  />
                </label>
                <label>
                  <span className="label">Remote policy</span>
                  <select
                    className="input"
                    value={
                      extracted.hard_constraints.remote == null
                        ? ""
                        : String(extracted.hard_constraints.remote)
                    }
                    onChange={(event) =>
                      updateHardConstraints({
                        remote:
                          event.target.value === ""
                            ? null
                            : event.target.value === "true",
                      })
                    }
                  >
                    <option value="">Not specified</option>
                    <option value="true">Remote</option>
                    <option value="false">On-site / not remote</option>
                  </select>
                </label>
              </div>
            </div>
            <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-ink p-4 text-white dark:bg-black">
              <p className="text-sm">
                <strong>{selectedCount}</strong> resume
                {selectedCount === 1 ? "" : "s"} ×{" "}
                <strong>{extracted.requirements.length}</strong> focused
                judgments
              </p>
              <button
                className="button-acid"
                disabled={!canScore || Boolean(busy)}
                onClick={runMatch}
              >
                Score with Jev →
              </button>
            </div>
          </section>
        )}

        {busy && (
          <div className="fixed inset-x-0 bottom-6 mx-auto flex w-fit items-center gap-3 rounded-full bg-ink px-5 py-3 text-sm text-white shadow-lift dark:bg-acid dark:text-ink">
            <span className="spinner" />
            {busy}
          </div>
        )}

        {results.length > 0 && detail && (
          <section className="mt-10" aria-live="polite">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="eyebrow">Ranked results</p>
                <h2 className="font-display text-3xl font-black">
                  Evidence at a glance
                </h2>
              </div>
              <button className="button-secondary" onClick={exportCSV}>
                Export CSV
              </button>
            </div>
            {results.length > 1 && (
              <div className="panel mb-6 overflow-x-auto p-0">
                <table className="w-full text-left">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Resume</th>
                      <th>Score</th>
                      <th>Verdict</th>
                      <th>Review</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((result, index) => (
                      <tr
                        className="cursor-pointer"
                        key={`${result.resume_name}-${index}`}
                        onClick={() => setActiveResult(index)}
                      >
                        <td>
                          {result.status === "scored" ? `#${index + 1}` : "—"}
                        </td>
                        <td className="font-bold">{result.resume_name}</td>
                        <td>
                          {result.status === "scored"
                            ? (result.match_score ?? 0).toFixed(1)
                            : "Not scored"}
                        </td>
                        <td>
                          {result.status === "rejected"
                            ? "rejected before scoring"
                            : result.verdict.replaceAll("_", " ")}
                        </td>
                        <td>
                          {result.requires_human_review ? "Required" : "No"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
              <aside className="panel h-fit text-center">
                {detail.status === "scored" ? (
                  <div
                    className="score-ring"
                    style={
                      {
                        "--score": `${(detail.match_score ?? 0) * 3.6}deg`,
                      } as React.CSSProperties
                    }
                  >
                    <div>
                      <strong>{(detail.match_score ?? 0).toFixed(0)}</strong>
                      <span>/100</span>
                    </div>
                  </div>
                ) : (
                  <div className="mx-auto grid h-36 w-36 place-items-center rounded-full border-8 border-rose-200 bg-rose-50 text-sm font-black uppercase text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200">
                    Not scored
                  </div>
                )}
                <h3 className="mt-5 font-display text-xl font-black">
                  {detail.resume_name}
                </h3>
                <span className="badge mt-3">
                  {detail.status === "rejected"
                    ? "rejected before scoring"
                    : detail.verdict.replaceAll("_", " ")}
                </span>
                {detail.status === "scored" && detail.requires_human_review && (
                  <p className="mt-4 rounded-lg bg-amber-100 p-3 text-left text-xs text-amber-900">
                    Human review required due to uncertainty or a
                    hard-constraint flag.
                  </p>
                )}
                <dl className="mt-5 grid grid-cols-2 gap-2 text-left text-xs">
                  <div>
                    <dt>Seniority</dt>
                    <dd>{detail.seniority || "—"}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{detail.model_version}</dd>
                  </div>
                </dl>
              </aside>
              <div className="space-y-6">
                {detail.status === "rejected" && (
                  <div className="panel border-rose-300 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/30">
                    <h3 className="font-display text-xl font-black text-rose-900 dark:text-rose-100">
                      Rejected before model scoring
                    </h3>
                    <p className="mt-2 text-sm text-rose-800 dark:text-rose-200">
                      The app did not calculate or rank a match score for this
                      file.
                    </p>
                    <ul className="mt-4 list-disc space-y-2 pl-5 text-sm">
                      {detail.rejection_reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                    {detail.security_flags.length > 0 && (
                      <p className="mt-4 text-xs text-stone-500 dark:text-stone-300">
                        Security flags: {detail.security_flags.join(", ")}
                      </p>
                    )}
                  </div>
                )}
                {detail.status === "scored" && (
                  <>
                    <div className="panel overflow-x-auto">
                      <h3 className="mb-4 font-display text-xl font-black">
                        Requirement breakdown
                      </h3>
                      <table className="w-full min-w-[680px] text-left">
                        <thead>
                          <tr>
                            <th>Requirement</th>
                            <th>Evidence score</th>
                            <th>Confidence</th>
                            <th>Evidence</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detail.requirement_results.map((item) => (
                            <tr key={item.requirement.id}>
                              <td>
                                <strong>{item.requirement.text}</strong>
                                <small className="block text-stone-400">
                                  {item.requirement.kind.replaceAll("_", " ")} ·
                                  weight {item.requirement.weight}
                                </small>
                              </td>
                              <td>
                                <div className="bar">
                                  <span
                                    className={resultColor(
                                      item.normalized_score * 100,
                                    )}
                                    style={{
                                      width: `${item.normalized_score * 100}%`,
                                    }}
                                  />
                                </div>
                                <small>
                                  {Math.round(item.normalized_score * 100)}%
                                </small>
                              </td>
                              <td>
                                {item.confidence == null
                                  ? "—"
                                  : `${Math.round(item.confidence * 100)}%`}
                              </td>
                              <td className="max-w-sm text-xs text-stone-500 dark:text-stone-300">
                                {item.evidence.slice(0, 3).map((line) => (
                                  <p className="mb-1" key={line}>
                                    “{line}”
                                  </p>
                                ))}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="grid gap-6 md:grid-cols-2">
                      <div className="panel">
                        <h3 className="mb-3 font-display text-lg font-black">
                          Biggest gaps
                        </h3>
                        <ol className="space-y-2">
                          {detail.gaps.slice(0, 5).map((gap, index) => (
                            <li
                              className="flex gap-3 text-sm"
                              key={gap.requirement_id}
                            >
                              <span className="font-mono text-stone-400">
                                {String(index + 1).padStart(2, "0")}
                              </span>
                              <span>{gap.requirement}</span>
                            </li>
                          ))}
                        </ol>
                      </div>
                      <div className="panel">
                        <h3 className="mb-3 font-display text-lg font-black">
                          Hard constraints
                        </h3>
                        {detail.hard_constraint_checks.length ? (
                          detail.hard_constraint_checks.map((check) => (
                            <div
                              className="mb-2 flex justify-between gap-3 text-sm"
                              key={check.constraint}
                            >
                              <span>
                                {check.constraint}: {check.required}
                              </span>
                              <strong>
                                {check.passed == null
                                  ? "Verify"
                                  : check.passed
                                    ? "Pass"
                                    : "Flag"}
                              </strong>
                            </div>
                          ))
                        ) : (
                          <p className="empty">
                            No hard constraints extracted.
                          </p>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </section>
        )}
      </main>
      <footer className="mx-auto mt-16 max-w-7xl border-t border-black/10 px-5 py-8 text-xs text-stone-500 dark:border-white/10 lg:px-8">
        JevMatch ranks and flags. Hiring decisions belong to people. Review
        local automated-employment laws before real-world use.
      </footer>
    </div>
  );
}
