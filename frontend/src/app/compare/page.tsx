import { Suspense } from "react";

import { CompareView } from "@/components/CompareView";
import { LoadingBlock } from "@/components/ui";

export default function ComparePage() {
  return (
    <Suspense fallback={<LoadingBlock label="Preparing comparison" />}>
      <CompareView />
    </Suspense>
  );
}
