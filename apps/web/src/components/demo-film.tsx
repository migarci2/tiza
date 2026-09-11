import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import recording from "../../public/media/tiza-demo.json";
import en from "../locales/en.json";
const t = (key: keyof typeof en) => en[key];
export function DemoFilm() {
  const video = useRef<HTMLVideoElement>(null);
  const userPaused = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    const element = video.current!;
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    let visible = true;
    const sync = () => {
      if (preference.matches || userPaused.current || !visible) element.pause();
      else element.play().catch(() => setPlaying(false));
    };
    const observer = new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      sync();
    });
    observer.observe(element);
    preference.addEventListener("change", sync);
    return () => {
      observer.disconnect();
      preference.removeEventListener("change", sync);
      element.pause();
    };
  }, []);
  const toggle = () => {
    const element = video.current!;
    userPaused.current = playing;
    if (playing) element.pause();
    else element.play().catch(() => setError(true));
  };
  return (
    <figure className="demo-film">
      <span className="demo-film-circle" aria-hidden="true" />
      <div className="demo-film-screen">
        <video
          ref={video}
          src="/media/tiza-demo.mp4"
          poster="/media/tiza-demo-poster.png"
          width="1280"
          height="800"
          muted
          loop
          playsInline
          preload="metadata"
          aria-label={t("film.alt")}
          aria-describedby="demo-film-description"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onError={() => setError(true)}
        />
        <button
          className="demo-film-toggle"
          type="button"
          onClick={toggle}
          disabled={error}
          data-paused={!playing}
          aria-label={playing ? t("film.pause") : t("film.play")}
        >
          {playing ? <Pause size={17} /> : <Play size={17} />}
        </button>
      </div>
      <figcaption className="sr-only" id="demo-film-description">
        <p>
          {"agent_trace_illustrated" in recording &&
          recording.agent_trace_illustrated
            ? t("film.illustrated")
            : recording.model_invoked
              ? t("film.live")
              : t("film.local")}
        </p>
      </figcaption>
      {error && <p role="alert">{t("film.error")}</p>}
    </figure>
  );
}
