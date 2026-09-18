import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { handle, Cfg } from "../_shared/momentum.ts";

const cfg: Cfg = {
  key: "canada", label: "Canada Momentum", stateId: 3,
  portfolio: "canada-momentum-portfolio.json", cur: "C$",
  page: "https://bivarcapital.com/canada-momentum.html",
};

serve((req) => handle(req, cfg));
