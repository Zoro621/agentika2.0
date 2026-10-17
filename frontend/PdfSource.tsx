import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { request } from "./api";

type Page = {
  image: string;
  width: number;
  height: number;
  boxes: number[][];
  highlight: string;
};
export default function PdfSource({
  caseId,
  artifactId,
  initialPage = 1,
  pages,
  quote = "",
  box,
}: {
  caseId: string;
  artifactId: string;
  initialPage?: number;
  pages: number;
  quote?: string;
  box?: number[];
}) {
  const [page, setPage] = useState(initialPage);
  useEffect(() => setPage(initialPage), [artifactId, initialPage, quote]);
  const query = useQuery({
    queryKey: ["pdf-page", caseId, artifactId, page, quote],
    queryFn: () =>
      request<Page>(
        `/cases/${caseId}/artifacts/${artifactId}/pages/${page}?quote=${encodeURIComponent(page === initialPage ? quote.slice(0, 1800) : "")}`,
      ),
    staleTime: Infinity,
    retry: 1,
  });
  const data = query.data;
  const boxes = data?.boxes.length
    ? data.boxes
    : box && page === initialPage
      ? [box]
      : [];
  return (
    <section className="pdf-source" aria-label="Rendered PDF source">
      <div className="pdf-toolbar">
        <strong>ORIGINAL PAGE</strong>
        <div>
          <button
            className="icon-button"
            aria-label="Previous PDF page"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft size={17} />
          </button>
          <span role="status">
            Page {page} of {pages}
          </span>
          <button
            className="icon-button"
            aria-label="Next PDF page"
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight size={17} />
          </button>
        </div>
      </div>
      {query.isPending && (
        <p className="pdf-message">
          <Loader2 className="spin" size={15} /> Rendering the source page…
        </p>
      )}
      {query.error && (
        <p className="pdf-message">
          This page could not be rendered.{" "}
          <button onClick={() => query.refetch()}>Retry</button> or open the
          original source.
        </p>
      )}
      {data && (
        <>
          <div className="pdf-page">
            <img
              src={data.image}
              alt={`Original PDF page ${page}${boxes.length ? ", with the cited passage highlighted" : ""}`}
            />
            <svg
              viewBox={`0 0 ${data.width} ${data.height}`}
              aria-hidden="true"
            >
              {boxes.map((b, i) => (
                <rect
                  key={i}
                  x={b[0]}
                  y={b[1]}
                  width={b[2] - b[0]}
                  height={b[3] - b[1]}
                  fill="#f2c779"
                  fillOpacity={0.36}
                  stroke="#c79127"
                  strokeWidth={0.5}
                />
              ))}
            </svg>
          </div>
          <p className="pdf-caption">
            {boxes.length
              ? "Highlighted: cited source text or table region."
              : quote
                ? "No exact word geometry was found. Read the cited text and surrounding page."
                : "Original immutable source page."}
          </p>
        </>
      )}
    </section>
  );
}
