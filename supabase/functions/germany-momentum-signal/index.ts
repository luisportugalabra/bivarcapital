import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { handle, Cfg } from "../_shared/momentum.ts";

const cfg: Cfg = {
  key: "germany", label: "Germany Momentum", stateId: 4,
  portfolio: "germany-momentum-portfolio.json", cur: "€",
  page: "https://bivarcapital.com/germany-momentum.html",
};

serve((req) => handle(req, cfg));
