// Gold testbench for M2 (R8 + R9 + R10 + R11 in one run).
// Four resets, each placed against a different receiver state: mid-frame
// holding a handed-off A5 (R8), mid-bit with rxd held low through the release
// (R9), on the clock frame_error is high (R10), on the clock overrun_error is
// high (R11). The two strobes come from exclusive branches of the stop-bit
// sample, so they need separate resets. Self-checking after each reset.
`timescale 1ns / 1ps

module tb;

  localparam logic [15:0] PRESCALE = 16'd5;
  localparam int BIT = 5 * 8;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid, busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
    .rxd(rxd), .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(PRESCALE)
  );

  // Drive on the falling edge so inputs are stable at every rising edge.
  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic send_bits(input logic [7:0] b);  // start + data, no stop
    rxd = 1'b0; wait_clks(BIT);
    for (int i = 0; i < 8; i++) begin rxd = b[i]; wait_clks(BIT); end
  endtask

  task automatic wait_for(input string what, ref logic sig);
    int n = 0;
    while (sig !== 1'b1) begin
      @(negedge clk);
      n++;  // not ++n inside the condition: Verilator 5.020 internal error
      if (n > 4 * BIT) $fatal(1, "%s never pulsed", what);
    end
  endtask

  task automatic reset_two(input logic rxd_during);
    rst = 1'b1; rxd = rxd_during; wait_clks(2);
    rst = 1'b0;
  endtask

  initial begin
    @(negedge clk);
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(10);

    // R8: hand off A5, start the next frame, reset while busy.
    send_bits(8'hA5); rxd = 1'b1; wait_clks(BIT + 5);
    if (m_axis_tvalid !== 1'b0 || m_axis_tdata !== 8'hA5) $fatal(1, "A5 not handed off");
    rxd = 1'b0; wait_clks(20);
    if (busy !== 1'b1) $fatal(1, "not busy before R8 reset");
    rst = 1'b1; rxd = 1'b1; wait_clks(1);
    if (busy || m_axis_tvalid || m_axis_tdata !== 8'h00) $fatal(1, "R8: outputs not cleared");
    wait_clks(1); rst = 1'b0; wait_clks(10);

    // R9: reset mid-bit with rxd low; rxd stays low through and after release.
    rxd = 1'b0; wait_clks(25);
    if (!busy) $fatal(1, "not mid-frame before R9 reset");
    reset_two(1'b0);
    wait_clks(1); if (busy) $fatal(1, "R9: busy rose too early");
    wait_clks(1); if (!busy) $fatal(1, "R9: busy did not rise on the second clock");
    wait_clks(BIT - 2);
    for (int i = 0; i < 8; i++) begin rxd = 1'b1; wait_clks(BIT); end
    rxd = 1'b1; wait_clks(2 * BIT);  // stop bit and idle; the FF word is consumed

    // R10: low stop bit, reset on the clock frame_error is high.
    send_bits(8'hA5); rxd = 1'b0;
    wait_for("frame_error", frame_error);
    reset_two(1'b1);
    if (frame_error !== 1'b0) $fatal(1, "R10: frame_error not cleared");
    wait_clks(10);

    // R11: A5 left unread, then 3C; reset on the clock overrun_error is high.
    m_axis_tready = 1'b0;
    send_bits(8'hA5); rxd = 1'b1; wait_clks(BIT);
    if (m_axis_tvalid !== 1'b1) $fatal(1, "R11: first word not pending");
    send_bits(8'h3C); rxd = 1'b1;
    wait_for("overrun_error", overrun_error);
    reset_two(1'b1);
    if (overrun_error !== 1'b0 || m_axis_tvalid !== 1'b0) $fatal(1, "R11: not cleared");
    wait_clks(10);

    $display("PASS gold M2");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end

endmodule
