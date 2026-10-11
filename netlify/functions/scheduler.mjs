// Runs every day at 15:55 UTC = 23:55 Beijing time (5 min before midnight).
// It only kicks off the background runner, which does the waiting + sending.
export default async (req, context) => {
  const base = context?.site?.url || process.env.URL;
  await fetch(new URL("/.netlify/functions/runner-background", base), {
    method: "POST",
    headers: { "x-cron-secret": process.env.ADMIN_PASSWORD || "" },
  });
};

export const config = { schedule: "55 15 * * *" };
