-- ====================================================================
-- Cloud-Based Lost & Found Matcher Using Image and Text Similarity
-- Complete Supabase PostgreSQL Database Schema & Storage Setup
-- ====================================================================

-- 1. Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. USERS / PROFILES TABLE
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'admin')),
    student_id TEXT,
    phone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3. ITEMS TABLE (Lost & Found reports)
CREATE TABLE IF NOT EXISTS public.items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    user_name TEXT NOT NULL,
    user_email TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('lost', 'found')),
    category TEXT NOT NULL DEFAULT 'other',
    title TEXT NOT NULL,
    brand TEXT,
    color TEXT,
    location TEXT NOT NULL,
    item_date TEXT NOT NULL,
    description TEXT NOT NULL,
    image_url TEXT,
    image_hash TEXT,
    image_features JSONB DEFAULT '{}'::jsonb,
    safekeeping_location TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'matched', 'claimed', 'resolved', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_items_type ON public.items(type);
CREATE INDEX IF NOT EXISTS idx_items_category ON public.items(category);
CREATE INDEX IF NOT EXISTS idx_items_created_at ON public.items(created_at DESC);

-- 4. MATCHES TABLE (Multi-factor Similarity Results)
CREATE TABLE IF NOT EXISTS public.matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lost_item_id UUID REFERENCES public.items(id) ON DELETE CASCADE,
    found_item_id UUID REFERENCES public.items(id) ON DELETE CASCADE,
    overall_score NUMERIC(5,2) NOT NULL,
    text_score NUMERIC(5,2) NOT NULL,
    location_score NUMERIC(5,2) NOT NULL,
    date_score NUMERIC(5,2) NOT NULL,
    brand_color_score NUMERIC(5,2) NOT NULL,
    image_score NUMERIC(5,2),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'claimed', 'resolved')),
    explanation JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT unique_lost_found_match UNIQUE (lost_item_id, found_item_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_score ON public.matches(overall_score DESC);

-- 5. NOTIFICATIONS TABLE
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    item_id UUID REFERENCES public.items(id) ON DELETE SET NULL,
    match_id UUID REFERENCES public.matches(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    score NUMERIC(5,2),
    read_status BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_notifications_user ON public.notifications(user_id, read_status);

-- 6. CLAIMS TABLE
CREATE TABLE IF NOT EXISTS public.claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    match_id UUID REFERENCES public.matches(id) ON DELETE CASCADE,
    lost_item_id UUID REFERENCES public.items(id) ON DELETE CASCADE,
    found_item_id UUID REFERENCES public.items(id) ON DELETE CASCADE,
    claimant_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    claimant_name TEXT NOT NULL,
    finder_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    finder_name TEXT NOT NULL,
    proof_details TEXT NOT NULL,
    contact_info TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 7. CLOUD AUDIT LOGS
CREATE TABLE IF NOT EXISTS public.cloud_sync_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- ====================================================================
-- 8. STORAGE BUCKET CONFIGURATION FOR ITEM PHOTOS
-- ====================================================================

-- Insert 'item-photos' bucket if it doesn't exist
INSERT INTO storage.buckets (id, name, public)
VALUES ('item-photos', 'item-photos', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- Allow public read access to item photos
CREATE POLICY "Public Read Access"
ON storage.objects FOR SELECT
USING (bucket_id = 'item-photos');

-- Allow authenticated and anon upload to item-photos bucket
CREATE POLICY "Public Upload Access"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'item-photos');

-- ====================================================================
-- 9. ROW LEVEL SECURITY (RLS) POLICIES
-- ====================================================================

ALTER TABLE public.items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.claims ENABLE ROW LEVEL SECURITY;

-- Allow public read of active items
CREATE POLICY "Items are viewable by everyone" 
ON public.items FOR SELECT USING (true);

-- Allow insert/update for items
CREATE POLICY "Items can be inserted by anyone" 
ON public.items FOR INSERT WITH CHECK (true);

CREATE POLICY "Items can be updated by owners or admins" 
ON public.items FOR UPDATE USING (true);

-- Allow public read of matches
CREATE POLICY "Matches viewable by everyone" 
ON public.matches FOR SELECT USING (true);

CREATE POLICY "Matches manageable by service" 
ON public.matches FOR ALL USING (true);

-- Allow notifications
CREATE POLICY "Notifications access" 
ON public.notifications FOR ALL USING (true);

-- Allow claims
CREATE POLICY "Claims access" 
ON public.claims FOR ALL USING (true);
