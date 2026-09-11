import en from "../locales/en.json";

export function SdkCredit() {
  return (
    <a
      className="sdk-credit"
      href="https://strandsagents.com/"
      target="_blank"
      rel="noopener noreferrer"
    >
      <span>{en["sdk.builtWith"]}</span>
      <img
        src="/brand/strands-agents.svg"
        alt="Strands Agents SDK"
        width="136"
        height="40"
      />
    </a>
  );
}
