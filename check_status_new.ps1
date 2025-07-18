try {
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/sync/status/e15c9a2f-8b32-4f4d-93d2-cabc49426c32" -Method GET
    Write-Host "Status: $($status.status)"
    if ($status.error) {
        Write-Host "Feil: $($status.error)"
    }
    if ($status.result) {
        Write-Host "Resultat: $($status.result | ConvertTo-Json -Depth 3)"
    }
} catch {
    Write-Host "Feil: $($_.Exception.Message)"
} 