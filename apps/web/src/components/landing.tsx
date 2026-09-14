import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUpRight,
  Check,
  ChevronRight,
  LoaderCircle,
} from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Session } from "../api/types";
import { Button } from "./ui/button";
import en from "../locales/en.json";
import "./landing.css";
import { DemoFilm } from "./demo-film";
import { SdkCredit } from "./sdk-credit";
const t = (key: keyof typeof en) => en[key];
const chapters = [
  { id: "goal", art: "/art/tiza-goal.png", color: "yellow" },
  { id: "practice", art: "/art/tiza-practice.png", color: "coral" },
  { id: "return", art: "/art/tiza-return.png", color: "blue" },
] as const;
const copy = (id: string, part: string) =>
  t(`story.${id}.${part}` as keyof typeof en);

function Access({
  onAuthenticated,
}: {
  onAuthenticated: (session: Session) => void;
}) {
  const [code, setCode] = useState("");
  const verify = useMutation({
    mutationFn: () => api.demoCode(code.trim()),
    onSuccess: onAuthenticated,
  });
  const error = verify.error;
  return (
    <section id="access" className="access-card" aria-labelledby="access-title">
      <h2 id="access-title">{t("demo.welcome")}</h2>
      <p className="access-description">{t("demo.description")}</p>
      <form
        className="access-form"
        onSubmit={(event) => {
          event.preventDefault();
          verify.mutate();
        }}
      >
        <label htmlFor="access-code">{t("demo.code")}</label>
        <input
          id="access-code"
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="none"
          required
          minLength={6}
          maxLength={64}
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
            verify.reset();
          }}
        />
        <Button type="submit" className="primary" disabled={verify.isPending}>
          {verify.isPending ? (
            <LoaderCircle className="spin" size={18} />
          ) : null}
          {t("demo.enter")}
          {!verify.isPending && <ChevronRight size={18} />}
        </Button>
        {error && (
          <p role="alert" className="form-error">
            {error instanceof TypeError ||
            (error instanceof ApiError && error.status >= 500)
              ? t("landing.networkError")
              : error.message}
          </p>
        )}
      </form>
      <p className="access-footnote">{t("demo.footnote")}</p>
    </section>
  );
}

function Story() {
  const track = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          if (entry.isIntersecting)
            setActive(Number((entry.target as HTMLElement).dataset.chapter));
      },
      { rootMargin: "-45% 0px -25% 0px", threshold: 0 },
    );
    track.current
      ?.querySelectorAll("[data-chapter]")
      .forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, []);
  return (
    <section
      className="tiza-story"
      id="how-it-works"
      aria-labelledby="story-heading"
    >
      <div className="story-intro">
        <div>
          <p className="story-kicker">{t("story.eyebrow")}</p>
          <h2 id="story-heading">
            {t("story.heading")}
            <br />
            <em>{t("story.headingEm")}</em>
          </h2>
        </div>
        <p>{t("story.intro")}</p>
      </div>
      <div className="story-track" ref={track}>
        <div className="story-stage" data-active-chapter={active}>
          <nav aria-label="The Tiza cycle">
            {chapters.map((chapter, i) => (
              <a
                key={chapter.id}
                href={`#story-${chapter.id}`}
                aria-current={active === i ? "step" : undefined}
                onClick={() => setActive(i)}
              >
                <span>0{i + 1}</span>
                {copy(chapter.id, "label")}
              </a>
            ))}
          </nav>
          <div className="story-scenes">
            {chapters.map((chapter, i) => (
              <figure
                className="story-scene"
                key={chapter.id}
                aria-hidden={active !== i}
              >
                <img
                  src={chapter.art}
                  alt={copy(chapter.id, "alt")}
                  width="900"
                  height="600"
                  loading="lazy"
                />
                <figcaption>
                  <span className={`story-dot ${chapter.color}`} />
                  {copy(chapter.id, "caption")}
                </figcaption>
              </figure>
            ))}
          </div>
          <p className="story-example">{t("story.example")}</p>
        </div>
        <div className="story-chapters">
          {chapters.map((chapter, i) => (
            <article
              className={`story-chapter ${chapter.color}`}
              id={`story-${chapter.id}`}
              data-chapter={i}
              key={chapter.id}
            >
              <span className="story-number">0{i + 1}</span>
              <h3>{copy(chapter.id, "title")}</h3>
              <p>{copy(chapter.id, "body")}</p>
              <p className="story-detail">{copy(chapter.id, "detail")}</p>
              <div className="story-takeaway">
                <Check size={16} />
                <span>{copy(chapter.id, "takeaway")}</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export function Welcome(props: {
  onAuthenticated: (session: Session) => void;
  inviteToken?: string;
}) {
  return (
    <div className="tiza-landing">
      <a className="story-skip" href="#access">
        {t("landing.signin")}
      </a>
      <header className="story-header">
        <a className="story-brand" href="/" aria-label="Tiza home">
          <img className="tiza-logo" src="/brand/tiza-logo.svg" alt="tiza" width="114" height="40" />
        </a>
        <nav aria-label="Main navigation">
          <a className="story-nav-how" href="#how-it-works">
            {t("landing.how")}
          </a>
          <a className="story-button small" href="#access">
            {t("story.signin")}
            <ArrowUpRight size={17} />
          </a>
        </nav>
      </header>
      <main>
        <section className="story-hero" aria-labelledby="landing-title">
          <div className="story-hero-copy">
            <p className="story-kicker">{t("story.heroEyebrow")}</p>
            <h1 id="landing-title">
              {t("story.heroFirst")}
              <br />
              <span>{t("story.heroSecond")}</span>
            </h1>
            <p className="story-dek">{t("story.heroBody")}</p>
            <div className="story-hero-actions">
              <a className="story-button" href="#access">
                {t("story.heroCta")}
                <ArrowUpRight size={20} />
              </a>
              <a className="story-text-link" href="#how-it-works">
                {t("story.seeCycle")}
                <ArrowDown size={16} />
              </a>
            </div>
            <SdkCredit />
          </div>
          <DemoFilm />
        </section>
        <Story />
        <section className="story-ending">
          <div className="story-ending-copy">
            <p className="story-kicker">{t("story.endingEyebrow")}</p>
            <h2>{t("story.endingTitle")}</h2>
            <p>{t("story.endingBody")}</p>
            <p className="story-ending-note">{t("landing.approval")}</p>
          </div>
          <Access {...props} />
        </section>
      </main>
      <footer className="story-footer">
        <a href="/" className="story-brand" aria-label="Tiza home">
          <img className="tiza-logo" src="/brand/tiza-logo.svg" alt="tiza" width="114" height="40" />
        </a>
        <p>{t("landing.footer")}</p>
        <a href="#access">{t("story.signin")} ↗</a>
      </footer>
    </div>
  );
}
