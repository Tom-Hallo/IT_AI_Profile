import { useEffect } from "react";

export function V10Entry() {
  useEffect(() => {
    const destination =
      "/talent-os/index.html" + window.location.search + window.location.hash;

    window.location.replace(destination);
  }, []);

  return null;
}
