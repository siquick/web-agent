import * as React from "react";

import { cn } from "../../lib/utils";

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  fallback?: string;
}

export const Avatar = React.forwardRef<HTMLDivElement, AvatarProps>(
  ({ className, fallback, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-muted text-sm font-medium text-muted-foreground",
        className,
      )}
      {...props}
    >
      {children ?? fallback}
    </div>
  ),
);

Avatar.displayName = "Avatar";
