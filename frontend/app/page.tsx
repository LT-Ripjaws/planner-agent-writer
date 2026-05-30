import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background">
      <section className="mx-auto flex min-h-screen w-full max-w-4xl items-center px-6 py-12">
        <div className="w-full space-y-6">
          <div className="space-y-3">
            <Badge variant="secondary">Scope 5</Badge>
            <h1 className="text-3xl font-semibold text-foreground">
              Planner Agent Writer
            </h1>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Workspace</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">Ready.</CardContent>
          </Card>
        </div>
      </section>
    </main>
  );
}
