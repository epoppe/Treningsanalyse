try {
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/sync/status/814b29ef-5321-4da0-9f80-860b9d05938a" -Method GET
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