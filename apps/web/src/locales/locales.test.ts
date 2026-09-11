import { expect, test } from "vitest";
import en from "./en.json";
import es from "./es.json";

test("Spanish and English expose the same product copy keys", () => {
  expect(Object.keys(es).sort()).toEqual(Object.keys(en).sort());
  expect(en["actions.publish"]).toBe("Approve & send");
});
