import classNames from "classnames";

const researchkitLogo = "/img/brand/researchkit-logo-dark.svg";

type InterstitialProps = {
  className?: string;
  contentClassName?: string;
  children: React.ReactNode;
  showLogo: boolean;
  title?: string;
};

export function Interstitial({
  className,
  contentClassName,
  children,
  showLogo,
  title,
}: InterstitialProps) {
  return (
    <div className={classNames("interstitial", className)}>
      {showLogo && (
        <img className="logo" src={researchkitLogo} alt="ResearchKit" />
      )}
      {title && <h1 className="h3 interstitial-header">{title}</h1>}
      <div className={classNames(contentClassName)}>{children}</div>
    </div>
  );
}
