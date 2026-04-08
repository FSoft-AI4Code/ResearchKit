import classNames from "classnames";

type Props = {
  open: boolean;
  title: string;
};

const ResearchKitRailIcon = ({ open, title }: Props) => {
  return (
    <span
      className={classNames("rk-rail-icon", {
        "rk-rail-icon-open": open,
      })}
      aria-label={title}
    >
      <svg aria-hidden="true" viewBox="0 0 128 128" focusable="false">
        <rect width="128" height="128" rx="28" fill="currentColor" />
        <rect
          x="44"
          y="16"
          width="40"
          height="12"
          rx="6"
          fill="var(--rk-rail-icon-accent)"
        />
        <path
          d="M28 38h24c10 0 18 8 18 18v32c-7-6-15-8-26-8H28Z"
          fill="var(--rk-rail-icon-page-left)"
        />
        <path
          d="M100 38H76c-10 0-18 8-18 18v32c7-6 15-8 26-8h16Z"
          fill="var(--rk-rail-icon-page-right)"
        />
        <path
          d="M64 38v56"
          stroke="var(--rk-rail-icon-accent)"
          strokeWidth="5"
          strokeLinecap="round"
        />
        <path
          d="M36 54h18M36 66h18M36 78h18M74 54h12M74 66h12M74 78h12"
          stroke="var(--rk-rail-icon-accent)"
          strokeWidth="5"
          strokeLinecap="round"
        />
        <circle cx="92" cy="90" r="10" fill="var(--rk-rail-icon-search)" />
        <path
          d="M99 97l13 13"
          stroke="var(--rk-rail-icon-search)"
          strokeWidth="6"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
};

export default ResearchKitRailIcon;
