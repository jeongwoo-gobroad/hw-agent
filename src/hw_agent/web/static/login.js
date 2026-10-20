document.querySelector("#login").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.target.querySelector("button");
  button.disabled = true;
  try {
    const data = Object.fromEntries(new FormData(event.target));
    const response = await fetch("/api/login", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail);
    location.href = "/";
  } catch (error) { document.querySelector("#error").textContent = error.message; }
  finally { button.disabled = false; }
});
