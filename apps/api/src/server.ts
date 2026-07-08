import { buildApp } from "./app.js";
import { createConfig } from "./config.js";

const config = createConfig();
const app = buildApp({ config });

await app.listen({ host: config.host, port: config.port });
