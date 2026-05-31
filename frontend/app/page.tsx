import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background">
      <section className="mx-auto flex min-h-screen w-full max-w-4xl items-center px-6 py-12">
        <div className="w-full space-y-6">
          <div className="space-y-3">
            <Badge variant="secondary">Scope 5</Badge>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">
              Planner Agent Writer
            </h1>
            <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
              The frontend foundation is ready for the topic form, run history,
              live progress stream, and Markdown result views.
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Frontend Foundation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-muted-foreground">
              <div className="grid gap-3 sm:grid-cols-3">
                <div>
                  <div className="font-medium text-foreground">Scaffold</div>
                  <div>Next.js App Router</div>
                </div>
                <div>
                  <div className="font-medium text-foreground">Data</div>
                  <div>Typed API wrappers</div>
                </div>
                <div>
                  <div className="font-medium text-foreground">UI</div>
                  <div>Shared primitives</div>
                </div>
              </div>
              <Separator />
              <Button disabled>UX starts in Scope 6</Button>
            </CardContent>
          </Card>
        </div>
      </section>
    </main>
  );
}
