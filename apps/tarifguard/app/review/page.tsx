import { ReviewForm } from "@/components/ReviewForm";

/**
 * The human-in-the-loop made operable. Records flagged requires_review show the raw extract
 * beside the ai_map proposal; the reviewer approves or corrects, and the record is frozen
 * server-side. This is the console's only write path, and it goes through the API
 * (app/api/review) — never the database, never freeze() directly.
 */
export default function ReviewPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-navy">Review queue</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-body">
          The point where an AI proposal becomes a frozen record. Each flagged record shows
          the deterministic raw extract beside the labelled AI proposal with its confidence.
          Approve to accept the proposal verbatim, or correct any field first — either way the
          freeze happens server-side.
        </p>
      </header>

      <ReviewForm />
    </div>
  );
}
