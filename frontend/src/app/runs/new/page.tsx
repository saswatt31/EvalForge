import { Suspense } from "react";

import { NewRunForm } from "@/components/NewRunForm";
import { LoadingBlock } from "@/components/ui";

export default function NewRunPage() {
  return (
    <Suspense fallback={<LoadingBlock label="Preparing the evaluation form" />}>
      <NewRunForm />
    </Suspense>
  );
}
