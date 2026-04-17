import "./Skeleton.css";

type Props = {
  width?: string | number;
  height?: string | number;
  circle?: boolean;
  className?: string;
};

export function Skeleton({ width, height, circle, className = "" }: Props) {
  const style = {
    width: width,
    height: height,
    borderRadius: circle ? "50%" : undefined,
  };

  return <div className={`skeleton ${className}`} style={style} />;
}
