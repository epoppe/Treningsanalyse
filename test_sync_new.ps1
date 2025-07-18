try {
    $body = @{
        start_date = "2024-12-01"
        end_date = "2024-12-02"
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/sync/activities" -Method POST -Body $body -ContentType "application/json"
    Write-Host "Ny sync startet: $($response.job_id)"
    
    # Vent litt og sjekk status
    Start-Sleep -Seconds 10
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/sync/status/$($response.job_id)" -Method GET
    Write-Host "Status: $($status.status)"
    
    if ($status.result) {
        Write-Host "Resultat: $($status.result | ConvertTo-Json -Depth 3)"
    }
    
} catch {
    Write-Host "Feil: $($_.Exception.Message)"
} 