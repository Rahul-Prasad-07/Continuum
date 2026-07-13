import { MARKUP } from "@/generated/markup";
import { SCRIPTS } from "@/generated/scripts";

// The marketing page is a faithful migration of the original static index.html.
// The body markup is server-rendered verbatim (great for SEO / no layout shift),
// and the original vanilla-JS behaviour (hero canvas, journey engine, typewriter,
// interactive demo, theme toggle) runs unchanged from the extracted <script> bodies.
// A display:contents wrapper keeps #bgfx fixed positioning and stacking identical
// to the original, where the markup were direct children of <body>.
export default function Page() {
  return (
    <>
      <div
        style={{ display: "contents" }}
        dangerouslySetInnerHTML={{ __html: MARKUP }}
      />
      {SCRIPTS.map((code, i) => (
        <script key={i} dangerouslySetInnerHTML={{ __html: code }} />
      ))}
    </>
  );
}
