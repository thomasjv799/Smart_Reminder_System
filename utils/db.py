import os
import psycopg2


def get_expiring_vehicles(days: int = 30) -> list[dict]:
    """Return vehicles with at least one expiry within [today-7d, today+days]."""
    sql = """
        SELECT
            nickname,
            registration_number,
            owner_name,
            insurance_valid_until,
            pucc_valid_until,
            fitness_valid_until,
            mv_tax_valid_until,
            permit_valid_until
        FROM vehicles
        WHERE
            insurance_valid_until BETWEEN CURRENT_DATE - INTERVAL '7 days'
                AND CURRENT_DATE + %(days)s * INTERVAL '1 day'
            OR pucc_valid_until BETWEEN CURRENT_DATE - INTERVAL '7 days'
                AND CURRENT_DATE + %(days)s * INTERVAL '1 day'
            OR fitness_valid_until BETWEEN CURRENT_DATE - INTERVAL '7 days'
                AND CURRENT_DATE + %(days)s * INTERVAL '1 day'
            OR mv_tax_valid_until BETWEEN CURRENT_DATE - INTERVAL '7 days'
                AND CURRENT_DATE + %(days)s * INTERVAL '1 day'
            OR (permit_valid_until IS NOT NULL
                AND permit_valid_until BETWEEN CURRENT_DATE - INTERVAL '7 days'
                    AND CURRENT_DATE + %(days)s * INTERVAL '1 day')
        ORDER BY LEAST(
            COALESCE(insurance_valid_until, '9999-01-01'::date),
            COALESCE(pucc_valid_until,      '9999-01-01'::date),
            COALESCE(fitness_valid_until,   '9999-01-01'::date),
            COALESCE(mv_tax_valid_until,    '9999-01-01'::date),
            COALESCE(permit_valid_until,    '9999-01-01'::date)
        )
    """
    with psycopg2.connect(os.environ["DATABASE_URI"]) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"days": days})
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
